-- Params:
--   :user_id   UUID
--   :year      INTEGER | NULL
--
SELECT
    a.type_id,
    a.sub_type_id,
    count(*) AS activity_count,
    sum(a.distance) AS total_distance,
    sum(a.duration) AS total_duration,
    sum(coalesce(nullif(a.moving_duration, interval '0'), a.duration)) AS total_effective_duration
FROM activities a
WHERE a.user_id = :user_id
  AND (
      CAST(:year AS integer) IS NULL
      OR extract(YEAR FROM a.start)::integer = CAST(:year AS integer)
  )
GROUP BY a.type_id, a.sub_type_id
ORDER BY a.type_id, a.sub_type_id;
