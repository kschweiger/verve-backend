-- verve_backend/queries/track_power_window.sql
--
-- Calculates the best average power over a rolling time window.
--
-- Fix: We compute the actual start of each window frame via MIN(time) OVER (...)
-- using the IDENTICAL frame specification as the AVG window. We then discard any
-- row whose real window span is less than the requested duration, which correctly
-- handles activities shorter than :minutes and any partial windows at the start
-- of a longer activity.
--
-- Parameters:
--   :minutes         - rolling window duration in minutes (e.g. 20 for 20-min power)
--   :activity_id     - the target activity UUID
--   :user_id         - the owning user UUID (required for RLS partition correctness)
--   :avg_over_windows - how many top windows to average together (e.g. top 3)

WITH power_windows AS (
  SELECT
    id,
    activity_id,
    user_id,
    time,
    power,
    -- Rolling average power over the requested duration
    AVG(power) OVER (
      PARTITION BY activity_id, user_id
      ORDER BY time
      RANGE BETWEEN INTERVAL '1 minute' * :minutes PRECEDING AND CURRENT ROW
    ) AS avg_window,
    -- Actual start of THIS window frame — must use identical PARTITION/ORDER/RANGE
    -- so PostgreSQL evaluates it over the same set of rows as AVG above.
    MIN(time) OVER (
      PARTITION BY activity_id, user_id
      ORDER BY time
      RANGE BETWEEN INTERVAL '1 minute' * :minutes PRECEDING AND CURRENT ROW
    ) AS window_start_time

  FROM track_points
  WHERE power IS NOT NULL
    AND activity_id = :activity_id
    AND user_id     = :user_id
),
-- Only keep rows whose window actually spans the full requested duration.
-- This eliminates:
--   (a) Activities shorter than :minutes entirely (no row ever passes).
--   (b) Partial windows at the beginning of a valid longer activity.
valid_windows AS (
  SELECT
    id,
    activity_id,
    user_id,
    time,
    avg_window
  FROM power_windows
  WHERE (time - window_start_time) >= INTERVAL '1 minute' * :minutes
)

SELECT
  AVG(avg_window)                              AS avg_of_top_X,
  ARRAY_AGG(time      ORDER BY avg_window DESC) AS top_window_times,
  ARRAY_AGG(id        ORDER BY avg_window DESC) AS top_window_ids,
  ARRAY_AGG(avg_window ORDER BY avg_window DESC) AS top_window_powers
FROM (
  SELECT *
  FROM valid_windows
  ORDER BY avg_window DESC
  LIMIT :avg_over_windows
) top_windows
GROUP BY activity_id, user_id;
