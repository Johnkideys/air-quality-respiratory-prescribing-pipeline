{{ config(materialized='table') }}

SELECT
    pollutant,
    COUNT(*)                       AS reading_count,
    COUNT(DISTINCT location_id)    AS num_stations
FROM {{ ref('int_monthly_air_quality') }}
GROUP BY pollutant
ORDER BY reading_count DESC