-- Params:
--   :user_id         UUID
--   :as_of_date       DATE
--
SELECT count(*) AS activities_this_month
FROM activities a
WHERE a.user_id = :user_id
  AND a.start >= date_trunc('month', CAST(:as_of_date AS date))
  AND a.start < date_trunc('month', CAST(:as_of_date AS date)) + interval '1 month';
