"""
Real-Time Feature Store — Unit Tests
Covers feature computation, Redis key formatting, and online/offline writers.
Redis and Snowflake are mocked — no infra required to run these.
"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ingestion.consumer import (
    FeatureComputer,
    FeatureStoreConfig,
    OnlineFeatureWriter,
    OfflineFeatureWriter,
)


# ── FeatureComputer ─────────────────────────────────────────────────────────

class TestFeatureComputer:

    def test_computes_expected_fields(self):
        event = {
            "user_id": "u1",
            "event_type": "add_to_cart",
            "timestamp": 1700000000,
            "session_duration": 120,
            "items_viewed": 4,
            "cart_value": 59.99,
            "device_type": "mobile",
        }
        features = FeatureComputer.from_user_event(event)

        assert features["user_id"] == "u1"
        assert features["event_type"] == "add_to_cart"
        assert features["session_duration_sec"] == 120
        assert features["items_viewed"] == 4
        assert features["cart_value_usd"] == 59.99
        assert features["is_mobile"] == 1

    def test_non_mobile_device(self):
        event = {"user_id": "u1", "device_type": "desktop"}
        features = FeatureComputer.from_user_event(event)
        assert features["is_mobile"] == 0

    def test_missing_user_id_raises(self):
        with pytest.raises(ValueError, match="user_id"):
            FeatureComputer.from_user_event({"event_type": "click"})

    def test_missing_optional_fields_default_safely(self):
        features = FeatureComputer.from_user_event({"user_id": "u1"})
        assert features["session_duration_sec"] == 0
        assert features["items_viewed"] == 0
        assert features["cart_value_usd"] == 0.0
        assert features["is_mobile"] == 0

    def test_event_ts_defaults_to_now_when_missing(self):
        before = int(time.time())
        features = FeatureComputer.from_user_event({"user_id": "u1"})
        after = int(time.time())
        assert before <= features["event_ts"] <= after

    def test_redis_key_format(self):
        key = FeatureComputer.redis_key("user-123", "user_features")
        assert key == "feature:user_features:user-123"


# ── OnlineFeatureWriter ──────────────────────────────────────────────────────

class TestOnlineFeatureWriter:

    def test_write_calls_hset_and_expire(self):
        config = FeatureStoreConfig()
        with patch("ingestion.consumer.redis.Redis") as mock_redis_cls:
            mock_redis = MagicMock()
            mock_pipe = MagicMock()
            mock_redis.pipeline.return_value = mock_pipe
            mock_redis_cls.return_value = mock_redis

            writer = OnlineFeatureWriter(config)
            writer.write({"user_id": "u1", "cart_value_usd": 10.0})

            mock_pipe.hset.assert_called_once()
            mock_pipe.expire.assert_called_once_with("feature:user_features:u1", config.feature_ttl_seconds)
            mock_pipe.execute.assert_called_once()

    def test_write_batch_processes_all_entities(self):
        config = FeatureStoreConfig()
        with patch("ingestion.consumer.redis.Redis") as mock_redis_cls:
            mock_redis = MagicMock()
            mock_pipe = MagicMock()
            mock_redis.pipeline.return_value = mock_pipe
            mock_redis_cls.return_value = mock_redis

            writer = OnlineFeatureWriter(config)
            batch = [{"user_id": f"u{i}", "cart_value_usd": 1.0} for i in range(5)]
            writer.write_batch(batch)

            assert mock_pipe.hset.call_count == 5
            assert mock_pipe.expire.call_count == 5
            mock_pipe.execute.assert_called_once()  # one round-trip for the whole batch


# ── OfflineFeatureWriter ─────────────────────────────────────────────────────

class TestOfflineFeatureWriter:

    def test_buffers_until_batch_max_size(self):
        config = FeatureStoreConfig(batch_max_size=3, batch_flush_interval_sec=9999)
        writer = OfflineFeatureWriter(config)

        with patch.object(writer, "flush") as mock_flush:
            writer.add({"user_id": "u1"})
            writer.add({"user_id": "u2"})
            mock_flush.assert_not_called()

            writer.add({"user_id": "u3"})
            mock_flush.assert_called_once()

    def test_flush_writes_batch_and_clears_buffer(self):
        config = FeatureStoreConfig()
        writer = OfflineFeatureWriter(config)
        writer._buffer = [{
            "user_id": "u1", "event_type": "click", "event_ts": 1700000000,
            "session_duration_sec": 10, "items_viewed": 1,
            "cart_value_usd": 0.0, "is_mobile": 0,
        }]

        with patch.object(writer, "_connect") as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            writer.flush()

            mock_conn.cursor.return_value.executemany.assert_called_once()
            mock_conn.commit.assert_called_once()
            mock_conn.close.assert_called_once()
        assert writer._buffer == []

    def test_flush_noop_on_empty_buffer(self):
        config = FeatureStoreConfig()
        writer = OfflineFeatureWriter(config)

        with patch.object(writer, "_connect") as mock_connect:
            writer.flush()
            mock_connect.assert_not_called()
