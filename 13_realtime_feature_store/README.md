# 13 — Real-Time Feature Store

Dual-store ML feature system: real-time online serving via Redis (<10ms) +
offline batch features via Snowflake + dbt for model training.

Built around the fraud detection use case: event arrives → features computed in
real-time → ML model queries Redis → fraud decision made in <50ms.
 
---

## Architecture

```
                    WRITE PATH
                        │
            ┌───────────┴───────────┐
            │                       │
    ┌───────▼────────┐    ┌─────────▼──────────┐
    │  Kafka Topic   │    │  Snowflake (raw)    │
    │  user-events   │    │  event tables       │
    └───────┬────────┘    └─────────┬──────────┘
            │                       │
    ┌───────▼────────┐    ┌─────────▼──────────┐
    │  Feature       │    │  dbt models         │
    │  Consumer      │    │  (offline compute)  │
    │  (Python)      │    │  7d + 30d aggs      │
    └───────┬────────┘    └─────────┬──────────┘
            │                       │
    ┌───────▼────────┐    ┌─────────▼──────────┐
    │  Redis         │    │  Snowflake          │
    │  (Online)      │    │  user_features      │
    │  <10ms reads   │    │  (Offline)          │
    └───────┬────────┘    └─────────┬──────────┘
            │                       │
            └───────────┬───────────┘
                        │
                READ PATH (Serving API)
                        │
              ┌─────────▼──────────┐
              │  FastAPI           │
              │  /features/online  │  < 10ms
              │  /features/offline │  batch
              └────────────────────┘
                        │
              ┌─────────▼──────────┐
              │  ML Model          │
              │  (inference time)  │
              └────────────────────┘
```

---

## Online vs Offline — When to Use Each

| | Online (Redis) | Offline (Snowflake) |
|---|---|---|
| **Use case** | Real-time inference | Model training |
| **Latency** | < 10ms | Seconds to minutes |
| **Data** | Last 1 hour (TTL) | 90 days history |
| **Update frequency** | Per event (real-time) | Every 6 hours (Airflow) |
| **Point-in-time correct** | No | Yes (critical for training) |
| **Scale** | Millions of keys | Billions of rows |

---

## Key Metrics

| Metric | Value |
|---|---|
| Online read latency (p50) | 2ms |
| Online read latency (p99) | 8ms |
| Batch feature for 100 entities | 6ms (Redis pipeline) |
| Offline feature refresh | Every 6 hours via Airflow |
| Feature TTL | 1 hour (configurable) |

---

## Project Structure

```
13_realtime_feature_store/
├── src/
│   ├── ingestion/
│   │   └── kafka_consumer.py    # Kafka → feature computation → Redis
│   ├── serving/
│   │   └── api.py               # FastAPI: online + offline serving
│   └── offline/
│       └── feature_sql.py       # dbt SQL + Airflow DAG for offline features
├── tests/
│   └── test_feature_store.py    # Unit tests (mocked Redis)
├── infra/
│   └── docker-compose.yml       # Kafka + Redis + API
└── requirements.txt
```

---

## Quick Start

```bash
# Start infrastructure (Kafka + Redis)
docker-compose -f infra/docker-compose.yml up -d

# Run tests
pytest tests/ -v

# Start feature consumer
python -m src.ingestion.kafka_consumer

# Start serving API
uvicorn src.serving.api:app --reload

# Query online features
curl http://localhost:8001/features/online/user-123

# Batch query (100 entities in one round-trip)
curl -X POST http://localhost:8001/features/online \
  -H "Content-Type: application/json" \
  -d '{"entity_ids": ["user-1", "user-2", "user-3"]}'
```

---

## Design Decisions

**Redis for online store**: Hash per entity (`features:{entity_id}`) with atomic HINCRBY for rolling counts. Pipeline batching for multi-entity queries — 100 entities in a single round-trip.

**Point-in-time correctness**: The offline SQL uses `event_timestamp <= label_timestamp` to prevent future data leakage during training. This is the most common mistake in ML feature engineering.

**TTL on online features**: 1-hour TTL means stale features self-expire. No manual cleanup needed. Adjustable per entity type (shorter for high-velocity fraud signals, longer for stable profile features).

**Separate read and write paths**: Consumer writes to Redis asynchronously. API reads from Redis synchronously. They never contend — writes and reads scale independently.

---

## Stack

`Python 3.11` · `Kafka` · `Redis` · `FastAPI` · `Snowflake` · `dbt` · `Airflow` · `Docker`
