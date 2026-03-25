"""
Real-Time Feature Store — Kafka Consumer
Consumes events, computes features, writes to Redis (online) and Snowflake (offline).

Two-tier architecture:
  Online store  (Redis)     → low-latency serving (<5ms) for real-time ML inference
  Offline store (Snowflake) → historical features for model training and backfill

This mirrors production feature stores at Uber (Michelangelo), Airbnb (Zipline),
and Spotify — a common system design interview question at FAANG.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import redis
from kafka import KafkaConsumer
import snowflake.connector

log = logging.getLogger(__name__)


@dataclass
class FeatureStoreConfig:
    # Kafka
    kafka_bootstrap: str = "localhost:9092"
    kafka_topic: str = "user_events"
    kafka_group_id: str = "feature-store-consumer"
    kafka_auto_offset: str = "earliest"

    # Online store — Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    feature_ttl_seconds: int = 86400  # 24h TTL; stale features auto-expire

    # Offline store — Snowflake
    sf_account: str = ""
    sf_user: str = ""
    sf_password: str = ""
    sf_database: str = "FEATURE_STORE"
    sf_schema: str = "ONLINE"
    sf_warehouse: str = "COMPUTE_WH"

    # Processing
    batch_flush_interval_sec: int = 60   # flush to Snowflake every 60s
    batch_max_size: int = 1000


class FeatureComputer:
    """
    Computes features from raw events.
    In production: these would be defined in a feature registry (Feast, Tecton).
    """

    @staticmethod
    def from_user_event(event: dict) -> dict:
        """
        Compute user-level features from a single event.
        Features are keyed by (entity_id, feature_name) for Redis lookup.
        """
        user_id = event.get("user_id")
        if not user_id:
            raise ValueError("Event missing user_id")

        features = {
            "user_id": user_id,
            "event_type": event.get("event_type"),
            "event_ts": event.get("timestamp", int(time.time())),
            # Computed features
            "session_duration_sec": event.get("session_duration", 0),
            "items_viewed": event.get("items_viewed", 0),
            "cart_value_usd": float(event.get("cart_value", 0.0)),
            "is_mobile": int(event.get("device_type") == "mobile"),
        }
        return features

    @staticmethod
    def redis_key(entity_id: str, feature_group: str) -> str:
        """Standardized Redis key format: feature:{group}:{entity_id}"""
        return f"feature:{feature_group}:{entity_id}"


class OnlineFeatureWriter:
    """
    Writes computed features to Redis for low-latency serving.
    Uses Redis Hash for efficient storage of multiple features per entity.
    """

    def __init__(self, config: FeatureStoreConfig):
        self.config = config
        self.r = redis.Redis(
            host=config.redis_host,
            port=config.redis_port,
            db=config.redis_db,
            decode_responses=True,
        )

    def write(self, features: dict, feature_group: str = "user_features"):
        entity_id = features["user_id"]
        key = FeatureComputer.redis_key(entity_id, feature_group)

        # Atomic write: update hash + set TTL
        pipe = self.r.pipeline()
        pipe.hset(key, mapping={k: str(v) for k, v in features.items()})
        pipe.expire(key, self.config.feature_ttl_seconds)
        pipe.execute()

    def write_batch(self, feature_list: list[dict], feature_group: str = "user_features"):
        pipe = self.r.pipeline()
        for features in feature_list:
            entity_id = features["user_id"]
            key = FeatureComputer.redis_key(entity_id, feature_group)
            pipe.hset(key, mapping={k: str(v) for k, v in features.items()})
            pipe.expire(key, self.config.feature_ttl_seconds)
        pipe.execute()
        log.info(f"Online write: {len(feature_list)} entities")


class OfflineFeatureWriter:
    """
    Writes features to Snowflake for historical storage and model training.
    Batched writes to reduce Snowflake compute cost.
    """

    def __init__(self, config: FeatureStoreConfig):
        self.config = config
        self._buffer: list[dict] = []
        self._last_flush = time.time()

    def _connect(self):
        return snowflake.connector.connect(
            account=self.config.sf_account,
            user=self.config.sf_user,
            password=self.config.sf_password,
            database=self.config.sf_database,
            schema=self.config.sf_schema,
            warehouse=self.config.sf_warehouse,
        )

    def add(self, features: dict):
        self._buffer.append(features)
        if (len(self._buffer) >= self.config.batch_max_size or
                time.time() - self._last_flush >= self.config.batch_flush_interval_sec):
            self.flush()

    def flush(self):
        if not self._buffer:
            return
        batch = self._buffer.copy()
        self._buffer.clear()
        self._last_flush = time.time()

        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.executemany("""
                INSERT INTO user_features
                    (user_id, event_type, event_ts, session_duration_sec,
                     items_viewed, cart_value_usd, is_mobile, written_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            """, [(
                f["user_id"], f["event_type"], f["event_ts"],
                f["session_duration_sec"], f["items_viewed"],
                f["cart_value_usd"], f["is_mobile"],
            ) for f in batch])
            conn.commit()
            log.info(f"Offline flush: {len(batch)} rows to Snowflake")
        finally:
            conn.close()


class FeatureStoreConsumer:
    """
    Kafka consumer that wires events -> features -> online + offline stores.
    Runs as a persistent service.
    """

    def __init__(self, config: FeatureStoreConfig = None):
        self.config = config or FeatureStoreConfig()
        self.computer = FeatureComputer()
        self.online = OnlineFeatureWriter(self.config)
        self.offline = OfflineFeatureWriter(self.config)
        self._processed = 0
        self._errors = 0

    def run(self):
        consumer = KafkaConsumer(
            self.config.kafka_topic,
            bootstrap_servers=self.config.kafka_bootstrap,
            group_id=self.config.kafka_group_id,
            auto_offset_reset=self.config.kafka_auto_offset,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        )
        log.info(f"Feature store consumer started: topic={self.config.kafka_topic}")

        for msg in consumer:
            try:
                features = FeatureComputer.from_user_event(msg.value)
                self.online.write(features)
                self.offline.add(features)
                self._processed += 1
                if self._processed % 100 == 0:
                    log.info(f"Processed {self._processed} events "
                             f"({self._errors} errors)")
            except Exception as e:
                self._errors += 1
                log.error(f"Event processing failed: {e} | raw={msg.value}")
