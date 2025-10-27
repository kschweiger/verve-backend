WITH grid_clusters AS (
    SELECT
        FLOOR(ST_X(geometry) / 10) * 10 as grid_x,
        FLOOR(ST_Y(geometry) / 10) * 10 as grid_y,
        COUNT(DISTINCT activity_id) as activity_count,
        COUNT(*) as total_point_count,
        ST_Centroid(ST_Collect(geometry)) as centroid_geom,
        array_agg(ST_Y(geography::geometry)) as cluster_latitudes,
        array_agg(ST_X(geography::geometry)) as cluster_longitudes
    FROM verve.track_points
    WHERE :activity_ids IS NULL OR activity_id = ANY(:activity_ids)
    GROUP BY grid_x, grid_y
)
SELECT
    ST_Y(ST_Transform(centroid_geom, 4326)) as latitude,
    ST_X(ST_Transform(centroid_geom, 4326)) as longitude,
    activity_count as point_count
FROM grid_clusters
ORDER BY point_count DESC;
