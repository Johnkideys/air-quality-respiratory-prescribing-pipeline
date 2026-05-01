WITH source AS (
    SELECT * FROM {{ source('raw', 'uk_stations') }}
),

renamed AS (
    SELECT
        -- identifiers
        location_id,
        name,

        -- geography
        latitude,
        longitude,

        -- sensor type flags
        is_monitor,
        is_mobile,

        -- available parameters
        has_pm25,
        pm25_sensor_id,
        has_pm10,
        pm10_sensor_id,
        has_no2,
        no2_sensor_id,

        -- derived
        CASE
            WHEN is_monitor = TRUE  THEN 'reference_monitor'
            WHEN is_monitor = FALSE THEN 'low_cost_sensor'
            ELSE 'unknown'
        END                                         AS monitor_type,

        (has_pm25 OR has_pm10 OR has_no2)           AS has_any_sensor,

        (CAST(has_pm25 AS INT64)
         + CAST(has_pm10 AS INT64)
         + CAST(has_no2 AS INT64))                  AS sensor_count,

        -- data quality flags
        latitude IS NULL
            OR longitude IS NULL                    AS is_missing_coordinates,
        latitude NOT BETWEEN -90 AND 90
            OR longitude NOT BETWEEN -180 AND 180   AS has_invalid_coordinates,
        name IS NULL                                AS is_missing_name

    FROM source
)

SELECT * FROM renamed