-- Params:
--   :user_id      UUID
--   :start_date   DATE
--   :end_date     DATE
--
SELECT
    CAST(a.start AS date) AS date,
    count(*) AS activity_count,
    sum(a.duration) AS total_duration,
    sum(coalesce(nullif(a.moving_duration, interval '0'), a.duration)) AS total_effective_duration
FROM activities a
WHERE a.user_id = :user_id
  AND a.start >= CAST(:start_date AS date)
  AND a.start <= CAST(:end_date AS date)  + interval '1 day'
GROUP BY CAST(a.start AS date)
ORDER BY CAST(a.start AS date);
