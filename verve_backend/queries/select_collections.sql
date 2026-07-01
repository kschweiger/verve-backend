-- verve_backend/queries/select_activity_collection_overviews.sql
--
-- Lists activity collections. Filters select matching collections, but the
-- returned aggregates always cover the full collection.
--
-- Parameters:
--   :year   - optional year filter based on collection activity dates
--   :month  - optional month filter based on collection activity dates; route requires year
--   :limit  - maximum number of collections to return
--   :offset - number of collections to skip


WITH matching_collections AS (
    SELECT DISTINCT
        c.id
    FROM
        activity_collections c
        JOIN activity_collection_links ac ON c.id = ac.collection_id
        JOIN activities a ON ac.activity_id = a.id
    WHERE
        (
            CAST(:year AS INTEGER) IS NULL
            OR EXTRACT(YEAR FROM a.start) = CAST(:year AS INTEGER)
        )
        AND (
            CAST(:month AS INTEGER) IS NULL
            OR EXTRACT(MONTH FROM a.start) = CAST(:month AS INTEGER)
        )
)
SELECT
    c.name,
    c.description,
    c.id,
    array_agg(a.id ORDER BY a.start, a.id) AS activity_ids,
    count(a.id) AS count,
    sum(a.distance) AS distance,
    sum(a.duration) AS duration,
    sum(a.moving_duration) AS moving_duration,
    sum(a.elevation_change_up) AS elevation_change_up,
    sum(a.elevation_change_down) AS elevation_change_down,
    min(a.start) AS "start",
    max(a.start + a.duration) AS "end"
FROM
    activity_collections c
    JOIN matching_collections mc ON mc.id = c.id
    JOIN activity_collection_links ac ON c.id = ac.collection_id
    JOIN activities a ON ac.activity_id = a.id
GROUP BY
    c.id
ORDER BY
    min(a.start) DESC,
    c.id
LIMIT :limit
OFFSET :offset;
