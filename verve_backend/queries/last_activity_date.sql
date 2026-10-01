-- Params:
--   :user_id         UUID
--   :after_today_at   TIMESTAMPTZ exclusive UTC bound
--   :timezone_name    TEXT IANA timezone
--
SELECT max((a.start AT TIME ZONE :timezone_name)::date) AS last_activity_date
FROM activities a
WHERE a.user_id = :user_id
  AND a.start < CAST(:after_today_at AS TIMESTAMPTZ)
