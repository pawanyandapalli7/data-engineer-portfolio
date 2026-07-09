# 13 — Real-Time Feature Store

> Dual-store ML feature system: Redis online serving (<10ms) + Snowflake offline batch.  
> Built around fraud detection: event arrives → features updated → ML inference in <50ms end-to-end.

**Stack:** `Python 3.11` · `Kafka` · `Redis` · `FastAPI` · `Snowflake` · `dbt` · `Airflow` · `Docker`

---

## Why This Matters

The most common failure mode in production ML isn't model quality — it's feature quality. Models trained offline see clean, static datasets. In production, features arrive late, go stale, or get computed differently between training and serving. This is called **training-serving skew**, and it silently kills model performance.

This feature store solves that with two rules:
1. **One pipeline, two outputs** — the same feature computation writes to Redis (serving) and Snowflake (training). The features are always identical.
2. **Point-in-time correctness** — offline SQL uses `event_timestamp <= label_timestamp` to prevent future data leakage during training.

This implements the standard online/offline feature store pattern used for fraud-detection and risk-scoring systems, where both inference-time latency and point-in-time training correctness are required.

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
    │  Consumer      │    │  7d + 30d aggs      │
    └───────┬────────┘    └─────────┬──────────┘
            │                       │
    ┌───────▼────────┐    ┌─────────▼──────────┐
    │  Redis         │    │  Snowflake          │
    │  (Online)      │    │  user_features      │
    │  <10ms reads   │    │  (Offline/Training) │
    └───────┬────────┘    └─────────┬──────────┘
            │                       │
            └───────────┬───────────┘
                        │
                READ PATH (Serving API)
                        │
              ┌─────────▼──────────┐
              │  FastAPI           │
              │  GET  /features/{id}        < 10ms
              │  POST /features/batch       pipeline
              └────────────────────┘
```

---

## Online vs Offline

| | Online (Redis) | Offline (Snowflake) |
|---|---|---|
| **Use case** | Real-time inference | Model training |
| **Latency** | <10ms | Seconds–minutes |
| **Data window** | 1 hour TTL | 90 days history |
| **Update frequency** | Per event (real-time) | Every 6 hours (Airflow) |
| **Point-in-time correct** | No | Yes — prevents training leakage |
| **Scale** | Millions of keys | Billions of rows |

---

## Performance Targets

| Metric | Target |
|---|---|
| Single entity read (p50) | ~2ms |
| Single entity read (p99) | <10ms |
| Batch (100 entities, 1 round-trip) | ~6ms |
| Offline feature refresh | Every 6 hours via Airflow |
| Feature TTL | 1 hour (configurable) |

*These are the design targets Redis's single-digit-ms read latency and pipelined batch reads are built for, not measured production benchmarks — this is a self-directed project, not a deployed system under real load.*

---

## Key Design Decisions

**Redis Hash per entity** — `feature:{group}:{entity_id}` stores all features in a single hash. `HGETALL` returns everything in one round-trip. `HMGET` returns specific fields. Atomic `HINCRBY` for rolling counts.

**Pipeline batching** — 100 entities in a single Redis round-trip via `pipeline()`. No N+1 reads. This is how you hit <10ms p99 at scale.

**TTL-based expiry** — 1-hour TTL means stale features self-expire. No manual cleanup job. Adjustable per feature type: shorter for high-velocity fraud signals, longer for stable profile features.

**Separate read/write paths** — Consumer writes to Redis asynchronously. API reads synchronously. They never contend — each path scales independently.

**Point-in-time SQL** — The offline SQL joins on `event_timestamp <= label_timestamp`. This single line prevents the most common ML training mistake: accidentally using features from the future.

---

## Project Structure

```
13_realtime_feature_store/
├── src/
│   ├── ingestion/
│   │   └── consumer.py          # Kafka → feature computation → Redis + Snowflake
│   └── serving/
│       └── api.py               # FastAPI: single + batch feature serving
├── tests/
│   └── test_feature_store.py    # Unit tests (mocked Redis/Snowflake — no infra required)
├── infra/
│   └── docker-compose.yml       # Kafka + Zookeeper + Redis + Feature API
└── requirements.txt
```

> Offline feature computation (dbt models + Airflow DAG referenced above) is
> described at the design level in this README but not yet implemented in
> code — the online path (`consumer.py`, `api.py`) is what's actually built
> and tested.

---

## Quick Start

```bash
# Start infrastructure
docker-compose -f infra/docker-compose.yml up -d

# Run tests
pytest tests/ -v

# Start feature consumer (Kafka → Redis)
python -m src.ingestion.consumer

# Start serving API
uvicorn src.serving.api:app --reload --port 8001

# Single entity lookup
curl http://localhost:8001/features/get \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "user-123"}'

# Batch lookup (100 entities, 1 round-trip)
curl -X POST http://localhost:8001/features/batch \
  -H "Content-Type: application/json" \
  -d '{"entity_ids": ["user-1", "user-2", "user-3"]}'
```

---

## System Design Interview Angle

This project maps directly to the *"Design a feature store for a fraud detection system"* system design question at FAANG/MAANG companies. Key talking points:

- **Why not just use the database directly?** Database latency (5–50ms) vs Redis latency (<5ms). At 10K QPS, this difference compounds.
- **Why dual-store instead of one source of truth?** Training and serving have fundamentally different access patterns. Optimizing for one degrades the other.
- **How do you handle feature drift?** TTL-based expiry + offline refresh pipeline ensures online features are never more than 1 hour stale.
- **How do you scale this?** Read path (Redis cluster) and write path (Kafka partitions) scale independently. Batch API uses pipelining to avoid O(N) round-trips.
