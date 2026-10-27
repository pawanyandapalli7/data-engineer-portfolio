-- Separate compute per workload so a heavy backfill can't slow dashboards,
-- with aggressive auto-suspend and a hard credit ceiling.
CREATE WAREHOUSE IF NOT EXISTS wh_ingest
  WAREHOUSE_SIZE = XSMALL AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE
  COMMENT = 'Loads and transforms';

CREATE WAREHOUSE IF NOT EXISTS wh_bi
  WAREHOUSE_SIZE = SMALL AUTO_SUSPEND = 300 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE
  MIN_CLUSTER_COUNT = 1 MAX_CLUSTER_COUNT = 3 SCALING_POLICY = STANDARD  -- multi-cluster: Enterprise edition
  COMMENT = 'Dashboards: scale out for concurrency, not up';

-- Kill runaway queries instead of paying for them.
ALTER WAREHOUSE wh_bi SET STATEMENT_TIMEOUT_IN_SECONDS = 900;

CREATE RESOURCE MONITOR IF NOT EXISTS rm_monthly
  WITH CREDIT_QUOTA = 100 FREQUENCY = MONTHLY START_TIMESTAMP = IMMEDIATELY
  TRIGGERS ON 80 PERCENT DO NOTIFY
           ON 100 PERCENT DO SUSPEND
           ON 110 PERCENT DO SUSPEND_IMMEDIATE;

ALTER WAREHOUSE wh_ingest SET RESOURCE_MONITOR = rm_monthly;
ALTER WAREHOUSE wh_bi     SET RESOURCE_MONITOR = rm_monthly;
