WITH filtered_points AS (
    SELECT
        id,
        activity_id,
        segment_id,
        time,
        elevation,
        heartrate,
        cadence,
        power,
        geography,
        geometry,
        ST_Distance(
            geography,
            LAG(geography) OVER (ORDER BY time)
        ) as distance_from_previous
    FROM verve.track_points
    WHERE activity_id = :activity_id
),
kept_points AS (
    SELECT *
    FROM filtered_points
    WHERE distance_from_previous IS NULL
       OR distance_from_previous > :min_distance
),
recalculated_distances AS (
    SELECT
        id,
        activity_id,
        segment_id,
        time,
        elevation,
        heartrate,
        cadence,
        power,
        geography,
        geometry,
        ST_Distance(
            geography,
            LAG(geography) OVER (ORDER BY time)
        ) as distance_from_previous,
        EXTRACT(EPOCH FROM (
            time - LAG(time) OVER (ORDER BY time)
        )) as time_diff_seconds
    FROM kept_points
)
SELECT
    id,
    activity_id,
    segment_id,
    time,
    elevation,
    heartrate,
    cadence,
    power,
    ST_Y(geography::geometry) as latitude,
    ST_X(geography::geometry) as longitude,
    distance_from_previous,
    time_diff_seconds,
    SUM(distance_from_previous) OVER (ORDER BY time) as cumulative_distance_m,
    SUM(distance_from_previous) OVER (ORDER BY time) / 1000.0 as cumulative_distance_km,
    SUM(time_diff_seconds) OVER (ORDER BY time) as cumulative_time_seconds
FROM recalculated_distances
ORDER BY time;
