WITH filtered AS (
    SELECT *
    FROM {{ ref('stg_openaq_measurements') }}
    WHERE is_negative_value = FALSE
      AND measured_at IS NOT NULL
),

aggregated AS (
    SELECT
        location_id,
        pollutant,
        DATE_TRUNC(measured_date, MONTH)    AS month,
        AVG(measured_value)                 AS avg_value,
        MIN(measured_value)                 AS min_value,
        MAX(measured_value)                 AS max_value,
        COUNT(*)                            AS reading_count,
        ANY_VALUE(unit)                     AS unit,
        ANY_VALUE(latitude)                 AS latitude,
        ANY_VALUE(longitude)                AS longitude

    FROM filtered
    GROUP BY location_id, pollutant, DATE_TRUNC(measured_date, MONTH)
)

SELECT * FROM aggregated