-- fct_journal_lines is the largest, append-heavy table and is almost always
-- queried by period and account. Cluster on (cast(date_trunc('month', posted_at) as date), account_id)
-- so Snowflake prunes micro-partitions for the common
-- `where posted_at between ... and account_id = ...` access pattern,
-- cutting scanned bytes on the reconciliation queries.

alter table subledger.analytics.fct_journal_lines
  cluster by (cast(date_trunc('month', posted_at) as date), account_id);

-- Inspect clustering health before/after with:
--   select system$clustering_information('subledger.analytics.fct_journal_lines',
--          '(cast(date_trunc(''month'', posted_at) as date), account_id)');
