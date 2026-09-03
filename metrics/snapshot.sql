\set ON_ERROR_STOP on
\pset tuples_only on
\pset format unaligned

SELECT jsonb_build_object(
  'sampled_at', clock_timestamp(),
  'database', (
    SELECT jsonb_build_object(
      'xact_commit', xact_commit,
      'xact_rollback', xact_rollback,
      'blks_read', blks_read,
      'blks_hit', blks_hit,
      'tup_returned', tup_returned,
      'tup_fetched', tup_fetched,
      'tup_inserted', tup_inserted,
      'tup_updated', tup_updated,
      'tup_deleted', tup_deleted,
      'temp_files', temp_files,
      'temp_bytes', temp_bytes,
      'deadlocks', deadlocks,
      'blk_read_time_ms', blk_read_time,
      'blk_write_time_ms', blk_write_time
    )
    FROM pg_stat_database
    WHERE datname = current_database()
  ),
  'wal', (
    SELECT jsonb_build_object(
      'wal_records', wal_records,
      'wal_fpi', wal_fpi,
      'wal_bytes', wal_bytes::text,
      'wal_buffers_full', wal_buffers_full,
      'wal_write', wal_write,
      'wal_sync', wal_sync,
      'wal_write_time_ms', wal_write_time,
      'wal_sync_time_ms', wal_sync_time
    )
    FROM pg_stat_wal
  ),
  'connections', (
    SELECT jsonb_build_object(
      'total', count(*),
      'active', count(*) FILTER (WHERE state = 'active'),
      'idle_in_transaction', count(*) FILTER (WHERE state = 'idle in transaction'),
      'waiting', count(*) FILTER (WHERE wait_event_type IS NOT NULL)
    )
    FROM pg_stat_activity
    WHERE datname = current_database()
  ),
  'database_size_bytes', pg_database_size(current_database())
)::text;
