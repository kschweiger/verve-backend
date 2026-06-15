-- Params:
--   :user_id         UUID
--   :as_of_date       DATE
--
SELECT max(a.start)::date AS last_activity_date
FROM activities a
WHERE a.user_id = :user_id AND CAST(a.start AS date) <= CAST(:as_of_date AS date)
