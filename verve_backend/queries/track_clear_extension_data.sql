-- Params:
--   :user_id      UUID
--   :activity_id  UUID
--
UPDATE track_points
SET {__extension_name__} = NULL
WHERE user_id = :user_id
  AND activity_id = :activity_id
