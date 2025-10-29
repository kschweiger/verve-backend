SELECT
	date(start),
	sub_type_id,
	SUM(distance),
	SUM(elevation_change_up),
	SUM(duration)
FROM
	verve.activities
WHERE
	extract(WEEK FROM START) = :week
	AND extract(ISOYEAR FROM START) = :year
	AND type_id = 1
GROUP BY sub_type_id, date(start)
ORDER BY
	date(START) DESC;
