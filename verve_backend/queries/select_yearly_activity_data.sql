-- Params:
--   :user_id   UUID
--   :start_at  TIMESTAMPTZ | NULL, inclusive UTC start of the user's local year
--   :end_at    TIMESTAMPTZ | NULL, exclusive UTC end of the user's local year
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
  AND (CAST(:start_at AS TIMESTAMPTZ) IS NULL OR a.start >= CAST(:start_at AS TIMESTAMPTZ))
  AND (CAST(:end_at AS TIMESTAMPTZ) IS NULL OR a.start < CAST(:end_at AS TIMESTAMPTZ))
GROUP BY a.type_id, a.sub_type_id
ORDER BY a.type_id, a.sub_type_id;
