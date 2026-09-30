-- Params:
--   :user_id      UUID
--   :start_at     TIMESTAMPTZ inclusive UTC bound
--   :end_at       TIMESTAMPTZ exclusive UTC bound
--   :timezone_name TEXT IANA timezone
--
SELECT
    (a.start AT TIME ZONE :timezone_name)::date AS date,
    count(*) AS activity_count,
    sum(a.duration) AS total_duration,
    sum(coalesce(nullif(a.moving_duration, interval '0'), a.duration)) AS total_effective_duration
FROM activities a
WHERE a.user_id = :user_id
  AND a.start >= CAST(:start_at AS TIMESTAMPTZ)
  AND a.start < CAST(:end_at AS TIMESTAMPTZ)
GROUP BY date
ORDER BY date;
