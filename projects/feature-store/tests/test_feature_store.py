"""
Real-time feature store: tests.

* Online path runs against fakeredis (real Redis command semantics, no server).
* Offline training-set SQL runs on DuckDB.
* A parity test checks that online and offline compute the same velocity
  features for the same events, which is the training/serving skew check.
"""

import sys
import time
from pathlib import Path
from unittest.mock import patch

import duckdb
import fakeredis
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingestion.consumer import (  # noqa: E402
    FeatureComputer,
    FeatureStoreConfig,
    OfflineFeatureWriter,
    OnlineFeatureWriter,
    velocity_features,
)

T0 = 1_700_000_000


def event(user="u1", ts=T0, cart=0.0, eid=None, **extra):
    e = {"user_id": user, "timestamp": ts, "cart_value": cart, "event_type": "click", **extra}
    if eid:
        e["event_id"] = eid
    return FeatureComputer.from_user_event(e)


@pytest.fixture
def online():
    return OnlineFeatureWriter(FeatureStoreConfig(), client=fakeredis.FakeRedis(decode_responses=True))


# ── FeatureComputer ──────────────────────────────────────────────────────────


class TestFeatureComputer:
    def test_computes_expected_fields(self):
        f = FeatureComputer.from_user_event(
            {
                "user_id": "u1",
                "event_type": "add_to_cart",
                "timestamp": T0,
                "session_duration": 120,
                "items_viewed": 4,
                "cart_value": 59.99,
                "device_type": "mobile",
            }
        )
        assert (f["user_id"], f["event_type"], f["event_ts"]) == ("u1", "add_to_cart", T0)
        assert (f["session_duration_sec"], f["items_viewed"], f["cart_value_usd"], f["is_mobile"]) == (120, 4, 59.99, 1)

    def test_missing_user_id_raises(self):
        with pytest.raises(ValueError, match="user_id"):
            FeatureComputer.from_user_event({"event_type": "click"})

    def test_defaults_and_timestamp(self):
        before = int(time.time())
        f = FeatureComputer.from_user_event({"user_id": "u1", "device_type": "desktop"})
        assert f["cart_value_usd"] == 0.0 and f["is_mobile"] == 0
        assert before <= f["event_ts"] <= int(time.time())

    def test_event_id_is_deterministic_for_replays(self):
        raw = {"user_id": "u1", "timestamp": T0, "cart_value": 5}
        assert (
            FeatureComputer.from_user_event(raw)["event_id"] == FeatureComputer.from_user_event(dict(raw))["event_id"]
        )

    def test_key_formats(self):
        assert FeatureComputer.redis_key("user-123", "user_features") == "feature:user_features:user-123"
        assert FeatureComputer.events_key("user-123", "user_features") == "events:user_features:user-123"


# ── Online writer (fakeredis) ────────────────────────────────────────────────


class TestOnlineWriter:
    def test_velocity_windows(self, online):
        online.write(event(ts=T0 - 7200, cart=10, eid="a"))  # 2h ago: 24h window only
        online.write(event(ts=T0 - 600, cart=30, eid="b"))  # 10 min ago
        f = online.write(event(ts=T0, cart=5, eid="c"))
        assert f["event_count_1h"] == "2" and f["event_count_24h"] == "3"
        assert f["cart_value_sum_24h"] == "45.0" and f["cart_value_max_24h"] == "30.0"

    def test_events_older_than_24h_drop_out(self, online):
        online.write(event(ts=T0 - 90000, cart=100, eid="old"))
        f = online.write(event(ts=T0, cart=1, eid="new"))
        assert f["event_count_24h"] == "1" and f["cart_value_sum_24h"] == "1.0"

    def test_replayed_event_is_not_double_counted(self, online):
        e = event(ts=T0, cart=10, eid="same")
        online.write(e)
        f = online.write(e)
        assert f["event_count_24h"] == "1"

    def test_late_event_counts_but_does_not_overwrite_latest_fields(self, online):
        online.write(event(ts=T0, cart=50, eid="new", event_type="checkout"))
        f = online.write(event(ts=T0 - 60, cart=1, eid="late", event_type="view"))
        stored = online.r.hgetall("feature:user_features:u1")
        assert stored["event_type"] == "checkout" and stored["event_ts"] == str(T0)
        assert f["event_count_1h"] == "2" and stored["last_event_ts"] == str(T0)

    def test_ttl_is_set(self, online):
        online.write(event(eid="x"))
        ttl = online.r.ttl("feature:user_features:u1")
        assert 0 < ttl <= FeatureStoreConfig().feature_ttl_seconds

    def test_users_are_isolated(self, online):
        online.write(event(user="u1", eid="1"))
        f = online.write(event(user="u2", eid="2"))
        assert f["event_count_24h"] == "1"


# ── Offline writer ───────────────────────────────────────────────────────────


class TestOfflineWriter:
    def cfg(self, **kw):
        return FeatureStoreConfig(sf_account="acct", **kw)

    def test_buffers_until_batch_max_size(self):
        writer = OfflineFeatureWriter(self.cfg(batch_max_size=3, batch_flush_interval_sec=9999))
        with patch.object(writer, "flush") as flush:
            writer.add(event(eid="1"))
            writer.add(event(eid="2"))
            flush.assert_not_called()
            writer.add(event(eid="3"))
            flush.assert_called_once()

    def test_flush_writes_and_clears(self):
        writer = OfflineFeatureWriter(self.cfg())
        writer._buffer = [event(eid="1")]
        with patch.object(writer, "_connect") as connect:
            writer.flush()
            sql, rows = connect.return_value.cursor.return_value.executemany.call_args[0]
        assert sql.startswith("INSERT INTO user_features (event_id,") and rows[0][0] == "1"
        assert writer.pending == 0

    def test_failed_flush_keeps_rows_for_retry(self):
        writer = OfflineFeatureWriter(self.cfg())
        writer._buffer = [event(eid="1")]
        with patch.object(writer, "_connect") as connect:
            connect.return_value.cursor.return_value.executemany.side_effect = RuntimeError("warehouse down")
            with pytest.raises(RuntimeError):
                writer.flush()
        assert writer.pending == 1

    def test_disabled_without_snowflake_account(self):
        writer = OfflineFeatureWriter(FeatureStoreConfig())
        writer.add(event(eid="1"))
        assert writer.enabled is False and writer.pending == 0


class TestConfig:
    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("REDIS_HOST", "redis")
        monkeypatch.setenv("FS_FEATURE_TTL_SECONDS", "120")
        cfg = FeatureStoreConfig.from_env()
        assert cfg.redis_host == "redis" and cfg.feature_ttl_seconds == 120


# ── Offline training set (DuckDB) + online/offline parity ────────────────────

EVENTS = [  # (event_id, user, ts, cart)
    ("e1", "u1", T0 - 90000, 500.0),  # outside every window
    ("e2", "u1", T0 - 7200, 10.0),
    ("e3", "u1", T0 - 600, 30.0),
    ("e3", "u1", T0 - 600, 30.0),  # replayed duplicate
    ("e4", "u1", T0 + 60, 999.0),  # after the label: must not leak
    ("e5", "u2", T0 - 30, 7.5),
]
LABELS = [("u1", T0, True), ("u2", T0, False), ("u3", T0, False)]


@pytest.fixture
def training_set():
    db = duckdb.connect()
    db.execute("""CREATE TABLE user_features (event_id VARCHAR, user_id VARCHAR, event_type VARCHAR, event_ts BIGINT,
                  session_duration_sec INT, items_viewed INT, cart_value_usd DECIMAL(12,2), is_mobile INT,
                  written_at TIMESTAMP)""")
    db.execute("CREATE TABLE labels (user_id VARCHAR, label_ts BIGINT, is_fraud BOOLEAN)")
    for i, (eid, user, ts, cart) in enumerate(EVENTS):
        db.execute(
            "INSERT INTO user_features VALUES "
            "(?, ?, 'click', ?, 0, 0, ?, 0, TIMESTAMP '2026-01-01' + ?::INT * INTERVAL 1 SECOND)",
            [eid, user, ts, cart, i],
        )
    db.executemany("INSERT INTO labels VALUES (?, ?, ?)", LABELS)
    sql = (ROOT / "offline" / "training_set.sql").read_text()
    cur = db.execute(sql)
    cols = [d[0] for d in cur.description]
    return {(r[0]): dict(zip(cols, r)) for r in cur.fetchall()}


class TestTrainingSet:
    def test_no_future_leakage(self, training_set):
        u1 = training_set["u1"]
        assert u1["last_event_ts"] == T0 - 600 and float(u1["cart_value_max_24h"]) == 30.0

    def test_duplicates_removed_and_windows_applied(self, training_set):
        u1 = training_set["u1"]
        assert (u1["event_count_1h"], u1["event_count_24h"], float(u1["cart_value_sum_24h"])) == (1, 2, 40.0)

    def test_user_without_events_still_gets_a_row(self, training_set):
        u3 = training_set["u3"]
        assert u3["last_event_ts"] is None and u3["event_count_24h"] == 0

    def test_online_and_offline_agree(self, training_set):
        """Training/serving parity: same events -> same velocity features."""
        for user in ("u1", "u2"):
            members = {(f"{eid}|{cart}", ts) for eid, u, ts, cart in EVENTS if u == user and ts <= T0}
            online = velocity_features(sorted(members), T0)
            offline = training_set[user]
            assert online["event_count_1h"] == offline["event_count_1h"]
            assert online["event_count_24h"] == offline["event_count_24h"]
            assert online["cart_value_sum_24h"] == pytest.approx(float(offline["cart_value_sum_24h"]))
            assert online["cart_value_max_24h"] == pytest.approx(float(offline["cart_value_max_24h"]))


# ── Serving API ──────────────────────────────────────────────────────────────


class TestServingApi:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        import serving.api as api

        fake = fakeredis.FakeRedis(decode_responses=True)
        OnlineFeatureWriter(FeatureStoreConfig(), client=fake).write(event(user="u1", cart=12.5, eid="a"))
        with patch.object(api, "r", fake):
            yield TestClient(api.app)

    def test_single_lookup(self, client):
        body = client.post(
            "/features/get", json={"entity_id": "u1", "feature_names": ["cart_value_usd", "nope"]}
        ).json()
        assert body["found"] and body["features"] == {"cart_value_usd": "12.5"}

    def test_batch_lookup_reports_missing(self, client):
        body = client.post("/features/batch", json={"entity_ids": ["u1", "ghost"]}).json()
        assert body["entities_found"] == 1 and body["results"]["ghost"] == {}

    def test_health(self, client):
        assert client.get("/health").json()["status"] == "ok"
