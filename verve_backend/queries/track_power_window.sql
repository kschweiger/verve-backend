WITH power_windows AS (
  SELECT
    id,
    activity_id,
    user_id,
    time,
    power,
    AVG(power) OVER (
      PARTITION BY activity_id, user_id
      ORDER BY time
      RANGE BETWEEN INTERVAL '1 minute' * :minutes PRECEDING AND CURRENT ROW
    ) AS avg_window
  FROM track_points
  WHERE power IS NOT NULL
    AND activity_id = :activity_id
    AND user_id = :user_id
)
SELECT
  AVG(avg_window) AS avg_of_top_X,
  ARRAY_AGG(time ORDER BY avg_window DESC) AS top_window_times,
  ARRAY_AGG(id ORDER BY avg_window DESC) AS top_window_ids,
  ARRAY_AGG(avg_window ORDER BY avg_window DESC) AS top_window_powers
FROM (
  SELECT *
  FROM power_windows
  ORDER BY avg_window DESC
  LIMIT :avg_over_windows
) top_windows
GROUP BY activity_id, user_id;
