SELECT
	res.*
FROM (
	SELECT
		l.id AS location_id,
		tp.activity_id,
		min(ST_Distance (l.loc, tp.geography)) AS dist_meters,
		count(tp.activity_id)
	FROM
		locations l
		JOIN track_points tp ON l.user_id = tp.user_id
			AND ST_DWithin (l.loc, tp.geography, :match_distance_meters)
	WHERE (cast(:location_type_id AS int) IS NULL
		OR l.type_id = cast(:location_type_id AS int))
	AND (cast(:location_sub_type_id AS int) IS NULL
		OR l.sub_type_id = cast(:location_sub_type_id AS int))
GROUP BY
	tp.activity_id,
	l.id) res
	JOIN activities a ON a.id = res.activity_id
WHERE (cast(:activity_type_id AS int) IS NULL
	OR a.type_id = cast(:activity_type_id AS int))
AND (cast(:activity_sub_type_id AS int) IS NULL
	OR a.sub_type_id = cast(:activity_sub_type_id AS int))
