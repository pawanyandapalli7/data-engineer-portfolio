### Retry & Backfill Strategy

- Pipelines are idempotent
- Failed partitions can be reprocessed independently
- Late-arriving data handled using watermark windows
