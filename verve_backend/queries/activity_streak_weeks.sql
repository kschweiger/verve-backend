-- Params:
--   :user_id         UUID
--   :as_of_date       DATE
--
WITH params AS (
  SELECT date_trunc('week', CAST(:as_of_date AS date))::date AS current_week
),
active_weeks AS (
  SELECT DISTINCT date_trunc('week', a.start)::date AS week_start
  FROM activities a
  WHERE a.user_id = :user_id
    AND a.start < (SELECT current_week + interval '1 week' FROM params)
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
