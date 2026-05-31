{{ config(materialized='table') }}

WITH station_months AS (
    SELECT
        location_id,
        COUNT(DISTINCT month) AS months_with_data
    FROM {{ ref('int_monthly_air_quality') }}
    GROUP BY location_id
),
total_months AS (
    SELECT COUNT(DISTINCT month) AS total_months
    FROM {{ ref('int_monthly_air_quality') }}
)
SELECT
    sm.months_with_data,
    COUNT(*)            AS station_count,
    tm.total_months
FROM station_months sm
CROSS JOIN total_months tm
GROUP BY sm.months_with_data, tm.total_months
ORDER BY sm.months_with_data