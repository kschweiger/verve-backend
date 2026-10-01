-- Params:
--   :user_id         UUID
--   :current_week     DATE local Monday
--   :after_week_at    TIMESTAMPTZ exclusive UTC bound
--   :timezone_name    TEXT IANA timezone
--
WITH params AS (
  SELECT CAST(:current_week AS date) AS current_week
),
active_weeks AS (
  SELECT DISTINCT date_trunc('week', a.start AT TIME ZONE :timezone_name)::date AS week_start
  FROM activities a
  WHERE a.user_id = :user_id
    AND a.start < CAST(:after_week_at AS TIMESTAMPTZ)
),
week_series AS (
  SELECT generate_series(
    (SELECT current_week FROM params),
    COALESCE((SELECT min(week_start) FROM active_weeks), (SELECT current_week FROM params)),
    interval '-1 week'
  )::date AS week_start
),
ranked AS (
  SELECT
    s.week_start,
    EXISTS (
      SELECT 1 FROM active_weeks aw WHERE aw.week_start = s.week_start
    ) AS is_active,
    row_number() OVER (ORDER BY s.week_start DESC) - 1 AS weeks_back
  FROM week_series s
),
first_gap AS (
  SELECT min(weeks_back) AS gap_at
  FROM ranked
  WHERE NOT is_active
)
SELECT COALESCE((SELECT gap_at FROM first_gap), (SELECT count(*) FROM ranked), 0) AS current_active_week_streak;
