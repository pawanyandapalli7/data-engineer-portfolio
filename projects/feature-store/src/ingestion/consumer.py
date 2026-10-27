"""
Real-time feature store: Kafka consumer.

event -> point features (latest event) + rolling velocity features (1h / 24h)
      -> Redis (online, per-entity hash)  +  Snowflake (offline, event log)

Guarantees
----------
* At-least-once: Kafka offsets are committed only after the online write and a
  successful offline flush. A crash replays uncommitted events.
* Replays don't double count: every event is stored in a per-user sorted set
  keyed by its event_id, so the same event added twice is still one member.
* Late events can't overwrite newer state: the "latest event" fields are only
  replaced by an event at least as new as the newest one already seen.
"""

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, fields

import redis

log = logging.getLogger(__name__)

WINDOW_1H, WINDOW_24H = 3600, 86400


@dataclass
class FeatureStoreConfig:
    # Kafka
    kafka_bootstrap: str = "localhost:9092"
    kafka_topic: str = "user_events"
    kafka_group_id: str = "feature-store-consumer"
    kafka_auto_offset: str = "earliest"

    # Online store (Redis)
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    feature_ttl_seconds: int = 3600  # an idle user's features expire after 1h

    # Offline store (Snowflake)
    sf_account: str = ""
    sf_user: str = ""
    sf_password: str = ""
    sf_database: str = "FEATURE_STORE"
    sf_schema: str = "OFFLINE"
    sf_warehouse: str = "COMPUTE_WH"

    # Processing
    batch_flush_interval_sec: int = 60
    batch_max_size: int = 1000

    @classmethod
    def from_env(cls) -> "FeatureStoreConfig":
        """Read FS_<FIELD> env vars (e.g. FS_REDIS_HOST), plus REDIS_HOST / KAFKA_BOOTSTRAP_SERVERS shortcuts."""
        cfg = cls()
        aliases = {"redis_host": "REDIS_HOST", "kafka_bootstrap": "KAFKA_BOOTSTRAP_SERVERS"}
        for f in fields(cls):
            raw = os.environ.get(f"FS_{f.name.upper()}") or os.environ.get(aliases.get(f.name, "-"))
            if raw is not None:
                setattr(cfg, f.name, f.type(raw) if f.type in (int, float) else raw)
        return cfg


class FeatureComputer:
    """Turns one raw event into point-in-time event features."""

    @staticmethod
    def from_user_event(event: dict) -> dict:
        user_id = event.get("user_id")
        if not user_id:
            raise ValueError("Event missing user_id")
        return {
            "user_id": user_id,
            "event_id": event.get("event_id") or FeatureComputer.event_id(event),
            "event_type": event.get("event_type"),
            "event_ts": int(event.get("timestamp", time.time())),
            "session_duration_sec": event.get("session_duration", 0),
            "items_viewed": event.get("items_viewed", 0),
            "cart_value_usd": float(event.get("cart_value", 0.0)),
            "is_mobile": int(event.get("device_type") == "mobile"),
        }

    @staticmethod
    def event_id(event: dict) -> str:
        """Deterministic id for events that don't carry one, so replays dedupe."""
        return hashlib.sha256(json.dumps(event, sort_keys=True, default=str).encode()).hexdigest()[:24]

    @staticmethod
    def redis_key(entity_id: str, feature_group: str) -> str:
        return f"feature:{feature_group}:{entity_id}"

    @staticmethod
    def events_key(entity_id: str, feature_group: str) -> str:
        return f"events:{feature_group}:{entity_id}"


def velocity_features(members: list[tuple[str, float]], now_ts: float) -> dict:
    """Rolling aggregates from (member, ts) pairs where member = '<event_id>|<cart_value>'."""
    out = {"event_count_1h": 0, "event_count_24h": 0, "cart_value_sum_24h": 0.0, "cart_value_max_24h": 0.0}
    for member, ts in members:
        if ts > now_ts or ts <= now_ts - WINDOW_24H:
            continue
        value = float(member.rsplit("|", 1)[1])
        out["event_count_24h"] += 1
        out["cart_value_sum_24h"] += value
        out["cart_value_max_24h"] = max(out["cart_value_max_24h"], value)
        if ts > now_ts - WINDOW_1H:
            out["event_count_1h"] += 1
    out["cart_value_sum_24h"] = round(out["cart_value_sum_24h"], 2)
    return out


class OnlineFeatureWriter:
    """Writes the latest event fields plus rolling velocity features to a Redis hash per user."""

    def __init__(self, config: FeatureStoreConfig, client: redis.Redis = None):
        self.config = config
        self.r = client or redis.Redis(
            host=config.redis_host, port=config.redis_port, db=config.redis_db, decode_responses=True
        )

    def write(self, features: dict, feature_group: str = "user_features") -> dict:
        user = features["user_id"]
        hkey = FeatureComputer.redis_key(user, feature_group)
        zkey = FeatureComputer.events_key(user, feature_group)
        ts = int(features.get("event_ts", time.time()))
        member = (
            f"{features.get('event_id') or FeatureComputer.event_id(features)}|{features.get('cart_value_usd', 0.0)}"
        )

        # Round trip 1: record the event, trim the window, read the window back.
        pipe = self.r.pipeline(transaction=True)
        pipe.zadd(zkey, {member: ts})
        pipe.zrevrange(zkey, 0, 0, withscores=True)  # newest event seen so far
        pipe.zremrangebyscore(zkey, "-inf", f"({ts - WINDOW_24H}")
        pipe.zrangebyscore(zkey, ts - WINDOW_24H, "+inf", withscores=True)
        pipe.expire(zkey, max(self.config.feature_ttl_seconds, WINDOW_24H))
        _, newest, _, window, _ = pipe.execute()

        newest_ts = newest[0][1] if newest else ts
        aggregates = velocity_features(window, newest_ts)
        mapping = {k: str(v) for k, v in aggregates.items()}
        mapping["last_event_ts"] = str(int(newest_ts))
        if ts >= newest_ts:  # only a newest-or-equal event replaces the point features
            mapping.update({k: str(v) for k, v in features.items() if k != "event_id"})

        # Round trip 2: publish features.
        pipe = self.r.pipeline(transaction=True)
        pipe.hset(hkey, mapping=mapping)
        pipe.expire(hkey, self.config.feature_ttl_seconds)
        pipe.execute()
        return mapping

    def write_batch(self, feature_list: list[dict], feature_group: str = "user_features") -> None:
        for features in feature_list:
            self.write(features, feature_group)
        log.info("Online write: %d events", len(feature_list))


class OfflineFeatureWriter:
    """Buffers event features and appends them to Snowflake in batches (fewer, larger writes).

    With no Snowflake account configured the writer is disabled and the
    consumer runs online-only, which is how the local docker-compose stack runs.
    """

    COLUMNS = (
        "event_id",
        "user_id",
        "event_type",
        "event_ts",
        "session_duration_sec",
        "items_viewed",
        "cart_value_usd",
        "is_mobile",
    )

    def __init__(self, config: FeatureStoreConfig):
        self.config = config
        self._buffer: list[dict] = []
        self._last_flush = time.time()
        self.enabled = bool(config.sf_account)
        if not self.enabled:
            log.warning("Offline store disabled: no Snowflake account configured")

    def _connect(self):
        import snowflake.connector  # imported lazily so the online path runs without it

        return snowflake.connector.connect(
            account=self.config.sf_account,
            user=self.config.sf_user,
            password=self.config.sf_password,
            database=self.config.sf_database,
            schema=self.config.sf_schema,
            warehouse=self.config.sf_warehouse,
        )

    @property
    def pending(self) -> int:
        return len(self._buffer)

    def due(self) -> bool:
        return bool(self._buffer) and (
            len(self._buffer) >= self.config.batch_max_size
            or time.time() - self._last_flush >= self.config.batch_flush_interval_sec
        )

    def add(self, features: dict) -> None:
        if not self.enabled:
            return
        self._buffer.append(features)
        if self.due():
            self.flush()

    def flush(self) -> None:
        """Write the buffer. On failure the rows stay buffered and the error propagates."""
        if not self._buffer:
            return
        batch = list(self._buffer)
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.executemany(
                f"INSERT INTO user_features ({', '.join(self.COLUMNS)}, written_at) "
                f"VALUES ({', '.join(['%s'] * len(self.COLUMNS))}, CURRENT_TIMESTAMP)",
                [tuple(f.get(c) for c in self.COLUMNS) for f in batch],
            )
            conn.commit()
        finally:
            conn.close()
        del self._buffer[: len(batch)]
        self._last_flush = time.time()
        log.info("Offline flush: %d rows", len(batch))


class FeatureStoreConsumer:
    """Kafka -> features -> Redis + Snowflake, with manual offset commits (at-least-once)."""

    def __init__(self, config: FeatureStoreConfig = None):
        self.config = config or FeatureStoreConfig.from_env()
        self.online = OnlineFeatureWriter(self.config)
        self.offline = OfflineFeatureWriter(self.config)
        self.processed = 0
        self.errors = 0

    def handle(self, event: dict) -> None:
        features = FeatureComputer.from_user_event(event)
        self.online.write(features)
        self.offline.add(features)
        self.processed += 1

    def run(self) -> None:
        from kafka import KafkaConsumer

        consumer = KafkaConsumer(
            self.config.kafka_topic,
            bootstrap_servers=self.config.kafka_bootstrap,
            group_id=self.config.kafka_group_id,
            auto_offset_reset=self.config.kafka_auto_offset,
            enable_auto_commit=False,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        )
        log.info("Consumer started: topic=%s", self.config.kafka_topic)
        while True:
            # poll() returns even when the topic is quiet, so time-based flushes still happen.
            for records in consumer.poll(timeout_ms=1000).values():
                for msg in records:
                    try:
                        self.handle(msg.value)
                    except ValueError as e:  # bad event: log and skip, don't block the partition
                        self.errors += 1
                        log.error("Skipping bad event at offset %s: %s", msg.offset, e)
            if self.offline.due():
                self.offline.flush()
            if self.offline.pending == 0:
                consumer.commit()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    FeatureStoreConsumer().run()
