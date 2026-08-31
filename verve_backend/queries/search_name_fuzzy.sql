-- Three-stage name search
--
-- Stage 1 — case-insensitive prefix: supports autocomplete ("elys" → "ELYS Boulderloft")
-- Stage 2 — pg_trgm:                catches typos ("Swiming" → "Swimming")
-- Stage 3 — daitch_mokotoff:        catches phonetics ("Jon" → "John")
--
-- Parameters (SQLAlchemy bindparams):
--   :query      TEXT   — the raw search string
--   :threshold  FLOAT  — trigram similarity cutoff (default 0.3)
--   :limit      INT    — max rows to return
-- search_activity_tags_fuzzy.sql
WITH
  _cfg AS (
      SELECT set_config('pg_trgm.similarity_threshold', CAST(:threshold AS text), true)
      -- set_config(setting, value, is_local=true) is the SQL-function
      -- equivalent of SET LOCAL — scoped to the current transaction.
  )
SELECT
    id,
    name,
    score
FROM (
    SELECT DISTINCT ON (id)
        id,
        name,
        similarity(name, :query) AS score,
        name ILIKE :query || '%' AS is_prefix_match
    FROM {__table_name__}, _cfg          -- cross join forces CTE evaluation
    WHERE
        (
            name ILIKE :query || '%'
            OR name % :query
            OR daitch_mokotoff(name) && daitch_mokotoff(:query)
        )
    ORDER BY id, is_prefix_match DESC, similarity(name, :query) DESC
) ranked
ORDER BY is_prefix_match DESC, score DESC
LIMIT :limit;
