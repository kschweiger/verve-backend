SELECT
    l.name AS location_name,
    tp.activity_id,
    MIN(ST_Distance(l.loc, tp.geography)) as dist_meters,
    COUNT(tp.activity_id)
FROM locations l
JOIN track_points tp
    ON l.user_id = tp.user_id
    AND ST_DWithin(l.loc, tp.geography, :match_distacne_meters)
GROUP BY tp.activity_id, l.name
