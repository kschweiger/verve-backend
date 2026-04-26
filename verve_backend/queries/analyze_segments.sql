-- Params:
--   :segment_set_id  UUID
--   :user_id         UUID
--
-- Semantics:
--   Cuts are ordered by point_id ASC.
--   A cut point belongs to segment before cut.
--   Next segment starts with first point after previous cut.
--   Final segment is implicit.

WITH selected_set AS (
    SELECT
        id,
        activity_id,
        user_id
    FROM segment_sets
    WHERE id = :segment_set_id
      AND user_id = :user_id
),

track_bounds AS (
    SELECT
        MIN(tp.id) AS min_point_id,
        MAX(tp.id) AS max_point_id
    FROM track_points tp
    JOIN selected_set ss
      ON ss.activity_id = tp.activity_id
     AND ss.user_id = tp.user_id
),

ordered_cuts AS (
    SELECT
        sc.point_id,
        row_number() OVER (ORDER BY sc.point_id ASC) - 1 AS segment_index,
        lag(sc.point_id) OVER (ORDER BY sc.point_id ASC) AS previous_cut_point_id
    FROM segment_cuts sc
    JOIN selected_set ss
      ON ss.id = sc.set_id
     AND ss.user_id = sc.user_id
),

cut_segments AS (
    SELECT
        segment_index,
        previous_cut_point_id AS start_after_point_id,
        point_id AS end_point_id
    FROM ordered_cuts
),

final_segment AS (
    SELECT
        COALESCE(MAX(oc.segment_index) + 1, 0) AS segment_index,
        MAX(oc.point_id) AS start_after_point_id,
        tb.max_point_id AS end_point_id
    FROM track_bounds tb
    LEFT JOIN ordered_cuts oc ON true
    GROUP BY tb.max_point_id
),

segments AS (
    SELECT
        segment_index,
        start_after_point_id,
        end_point_id
    FROM cut_segments

    UNION ALL

    SELECT
        segment_index,
        start_after_point_id,
        end_point_id
    FROM final_segment
),

point_deltas AS (
    SELECT
        tp.id,
        tp.activity_id,
        tp.user_id,
        tp.time,
        tp.elevation,
        tp.heartrate,
        tp.cadence,
        tp.power,

        ST_Distance(
            tp.geography,
            lag(tp.geography) OVER track_order
        ) AS distance_m,

        EXTRACT(EPOCH FROM (
            tp.time - lag(tp.time) OVER track_order
        ))::double precision AS dt_s,

        tp.elevation - lag(tp.elevation) OVER track_order AS elevation_delta_m

    FROM track_points tp
    JOIN selected_set ss
      ON ss.activity_id = tp.activity_id
     AND ss.user_id = tp.user_id

    WINDOW track_order AS (
        PARTITION BY tp.activity_id, tp.user_id
        ORDER BY tp.id ASC
    )
),

point_metrics AS (
    SELECT
        *,
        CASE
            WHEN dt_s > 0 AND distance_m IS NOT NULL
            THEN distance_m / dt_s
            ELSE NULL
        END AS speed_m_s
    FROM point_deltas
)

SELECT
    ss.id AS segment_set_id,
    ss.activity_id,
    s.segment_index,

    COALESCE(s.start_after_point_id, tb.min_point_id) AS start_point_id,
    MIN(pm.id) AS first_included_point_id,
    s.end_point_id,

    COALESCE(boundary_pm.time, MIN(pm.time)) AS start_time,
    MAX(pm.time) AS end_time,

    COUNT(pm.id) AS point_count,

    SUM(pm.distance_m) AS distance_m,
    SUM(pm.dt_s) AS elapsed_s,

    SUM(pm.distance_m)
        / NULLIF(
            SUM(pm.dt_s) FILTER (WHERE pm.distance_m IS NOT NULL),
            0
        ) AS avg_speed_m_s,

    MAX(pm.speed_m_s) AS max_speed_m_s,
    MIN(pm.speed_m_s) AS min_speed_m_s,

    SUM(pm.dt_s) FILTER (WHERE pm.distance_m IS NOT NULL)
    / NULLIF(SUM(pm.distance_m), 0)
    * 1000.0 AS avg_pace_s_per_km,

    SUM(GREATEST(pm.elevation_delta_m, 0)) AS elevation_gain_m,
    SUM(ABS(LEAST(pm.elevation_delta_m, 0))) AS elevation_loss_m,

    AVG(pm.heartrate) FILTER (WHERE pm.heartrate IS NOT NULL) AS avg_heartrate,
    MAX(pm.heartrate) AS max_heartrate,
    MIN(pm.heartrate) AS min_heartrate,

    AVG(pm.cadence) FILTER (WHERE pm.cadence IS NOT NULL) AS avg_cadence,
    MAX(pm.cadence) AS max_cadence,
    MIN(pm.cadence) AS min_cadence,

    AVG(pm.power) FILTER (WHERE pm.power IS NOT NULL) AS avg_power,
    MAX(pm.power) AS max_power,
    MIN(pm.power) AS min_power

FROM selected_set ss
JOIN track_bounds tb ON true
JOIN segments s ON s.end_point_id IS NOT NULL

LEFT JOIN point_metrics boundary_pm
  ON boundary_pm.id = s.start_after_point_id

JOIN point_metrics pm
  ON (s.start_after_point_id IS NULL OR pm.id > s.start_after_point_id)
 AND pm.id <= s.end_point_id

GROUP BY
    ss.id,
    ss.activity_id,
    s.segment_index,
    s.start_after_point_id,
    s.end_point_id,
    tb.min_point_id,
    boundary_pm.time

ORDER BY s.segment_index ASC;

