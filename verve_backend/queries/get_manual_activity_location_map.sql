SELECT a.id, lal.location_id
FROM activities a
JOIN location_activity_links lal ON a.id = lal.activity_id
