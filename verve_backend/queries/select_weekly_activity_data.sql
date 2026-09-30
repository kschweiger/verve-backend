SELECT
    (start AT TIME ZONE :timezone_name)::date AS local_date,
    sub_type_id,
    SUM(distance),
    SUM(elevation_change_up),
    SUM(duration),
    SUM(COALESCE(NULLIF(moving_duration, interval '0'), duration)) AS total_effective_duration
FROM activities
WHERE user_id = :user_id
  AND start >= CAST(:start_at AS TIMESTAMPTZ)
  AND start < CAST(:end_at AS TIMESTAMPTZ)
  AND type_id = :activity_type_id
GROUP BY sub_type_id, local_date
ORDER BY local_date DESC;
