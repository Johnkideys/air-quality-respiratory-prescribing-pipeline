{{ config(materialized='table') }}

WITH filtered AS (
    SELECT *
    FROM {{ ref('stg_openaq_measurements') }}
    WHERE is_negative_value = FALSE
      AND measured_at IS NOT NULL
      AND is_respiratory_pollutant = TRUE
),

averaged_daily AS (

    SELECT
        location_id,
        pollutant,
        DATE_TRUNC(measured_date, DAY)    AS day,

        AVG(measured_value)                 AS avg_value,
        MIN(measured_value)                 AS min_value,
        MAX(measured_value)                 AS max_value,
        COUNT(*)                            AS daily_reading_count,
        ANY_VALUE(unit)                     AS unit,
        ANY_VALUE(latitude)                 AS latitude,
        ANY_VALUE(longitude)                AS longitude

    FROM filtered
    GROUP BY location_id, pollutant, DATE_TRUNC(measured_date, DAY)
),

averaged_monthly AS (
    SELECT
        location_id,
        pollutant,
        DATE_TRUNC(day, MONTH)    AS month,

        AVG(avg_value)                      AS avg_value,
        MIN(min_value)                      AS min_value,
        MAX(max_value)                      AS max_value,

        SUM(daily_reading_count)            AS reading_count,
        COUNT(*)                            AS days_with_data,

        ANY_VALUE(unit)                     AS unit,
        ANY_VALUE(latitude)                 AS latitude,
        ANY_VALUE(longitude)                AS longitude

    FROM averaged_daily
    GROUP BY location_id, pollutant, DATE_TRUNC(day, MONTH)
)

-- Drop station-months with insufficient daily coverage.
-- 70% threshold balances regulatory practice against
-- preserving low-cost sensor data which often has gappier coverage.
--SELECT * FROM averaged_monthly WHERE days_with_data >= CEIL(0.70 * EXTRACT(DAY FROM LAST_DAY(month)))
-- filter Out outlier values 
SELECT *
FROM averaged_monthly
WHERE days_with_data >= CEIL(0.70 * EXTRACT(DAY FROM LAST_DAY(month)))
  AND avg_value <= CASE
        WHEN pollutant = 'pm25' THEN 100   -- physically plausible UK ceiling
        WHEN pollutant = 'pm10' THEN 150
        WHEN pollutant = 'no2'  THEN 400
        WHEN pollutant = 'o3'   THEN 300
        WHEN pollutant = 'so2'  THEN 200
        ELSE 1e9
    END