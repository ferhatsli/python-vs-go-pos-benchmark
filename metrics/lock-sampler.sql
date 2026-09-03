\set ON_ERROR_STOP on
\pset tuples_only on
\pset format unaligned

WITH activity AS (
  SELECT
    a.pid,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.query_id,
    pg_blocking_pids(a.pid) AS blocked_by,
    (SELECT count(*) FROM pg_locks l WHERE l.pid = a.pid) AS backend_lock_count
  FROM pg_stat_activity a
  WHERE a.datname = current_database()
), waiting AS (
  SELECT *
  FROM activity
  WHERE wait_event_type = 'Lock' OR cardinality(blocked_by) > 0
)
SELECT jsonb_build_object(
  'sampled_at', clock_timestamp(),
  'connections_total', (SELECT count(*) FROM activity),
  'connections_active', (SELECT count(*) FROM activity WHERE state = 'active'),
  'waiting_count', (SELECT count(*) FROM waiting),
  'lock_count', (
    SELECT count(*)
    FROM pg_locks
    WHERE database = (SELECT oid FROM pg_database WHERE datname = current_database())
  ),
  'backends', COALESCE(
    (
      SELECT jsonb_agg(
        jsonb_build_object(
          'pid', pid,
          'state', state,
          'wait_event_type', wait_event_type,
          'wait_event', wait_event,
          'query_id', query_id,
          'blocked_by', to_jsonb(blocked_by),
          'backend_lock_count', backend_lock_count
        ) ORDER BY pid
      )
      FROM waiting
    ),
    '[]'::jsonb
  )
)::text;
