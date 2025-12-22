SELECT
    l.id AS location_id,
    tp.activity_id,
    MIN(ST_Distance(l.loc, tp.geography)) as dist_meters,
    COUNT(tp.activity_id)
FROM locations l
JOIN track_points tp
    ON l.user_id = tp.user_id
    AND ST_DWithin(l.loc, tp.geography, :match_distance_meters)
GROUP BY tp.activity_id, l.id
