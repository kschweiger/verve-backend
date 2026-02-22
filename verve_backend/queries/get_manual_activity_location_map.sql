SELECT
	a.id,
	lal.location_id
FROM
	activities a
	JOIN location_activity_links lal ON a.id = lal.activity_id
	JOIN locations l ON lal.location_id = l.id
WHERE (cast(:location_type_id AS int) IS NULL
	OR l.type_id = cast(:location_type_id AS int))
AND (cast(:location_sub_type_id AS int) IS NULL
	OR l.sub_type_id = cast(:location_sub_type_id AS int))
AND (cast(:activity_type_id AS int) IS NULL
	OR a.type_id = cast(:activity_type_id AS int))
AND (cast(:activity_sub_type_id AS int) IS NULL
	OR a.sub_type_id = cast(:activity_sub_type_id AS int))
