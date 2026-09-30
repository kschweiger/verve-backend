-- Params:
--   :user_id         UUID
--   :start_at         TIMESTAMPTZ inclusive UTC bound
--   :end_at           TIMESTAMPTZ exclusive UTC bound
--
SELECT count(*) AS activities_this_month
FROM activities a
WHERE a.user_id = :user_id
  AND a.start >= CAST(:start_at AS TIMESTAMPTZ)
  AND a.start < CAST(:end_at AS TIMESTAMPTZ);
