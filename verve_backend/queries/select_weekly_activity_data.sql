SELECT
	date(start),
	distance,
	elevation_change_up,
	duration
FROM
	verve.activities
WHERE
	extract(WEEK FROM start) = :week
	AND extract(ISOYEAR FROM start) = :year
  AND type_id = :activity_type_id
ORDER BY
	START DESC;
