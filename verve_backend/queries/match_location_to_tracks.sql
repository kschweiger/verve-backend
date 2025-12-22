SELECT activity_id, COUNT(*)
FROM verve.track_points
WHERE ST_DWithin(
  geography,
  ST_SetSRID(ST_MakePoint(:longitude,:latitude), 4326)::geography,
  :match_distance_meters
)
GROUP BY activity_id
