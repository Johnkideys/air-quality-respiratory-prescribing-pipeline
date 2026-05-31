{{ config(materialized='table') }}

WITH unique_sensor_locations AS (
    SELECT
        location_id,
        latitude,
        longitude
    FROM {{ ref('stg_locations') }}
    WHERE latitude IS NOT NULL
      AND longitude IS NOT NULL
      AND NOT has_invalid_coordinates
),

practices AS (
    SELECT
        practice_code,
        practice_name,
        latitude,
        longitude
    FROM {{ ref('stg_practice_locations') }}
    WHERE latitude IS NOT NULL
      AND longitude IS NOT NULL
      AND TRIM(practice_name) != ''
),

candidate_pairs AS (
    -- Bounding-box pre-filter: drops pairs clearly more than ~10km apart
    -- before computing the expensive Haversine. 0.10° lat ≈ 10km;
    -- 0.19° lon ≈ 10km at UK latitudes.
    SELECT
        p.practice_code,
        p.practice_name,
        p.latitude                              AS practice_lat,
        p.longitude                             AS practice_lon,
        s.location_id,
        s.latitude                              AS sensor_lat,
        s.longitude                             AS sensor_lon
    FROM practices p
    INNER JOIN unique_sensor_locations s
        ON ABS(p.latitude - s.latitude) <= 0.10
        AND ABS(p.longitude - s.longitude) <= 0.19
),

with_distance AS (
    SELECT
        *,
        6371 * ACOS(
            COS(practice_lat * ACOS(-1)/180) * COS(sensor_lat * ACOS(-1)/180)
            * COS((sensor_lon * ACOS(-1)/180) - (practice_lon * ACOS(-1)/180))
            + SIN(practice_lat * ACOS(-1)/180) * SIN(sensor_lat * ACOS(-1)/180)
        ) AS distance_km
    FROM candidate_pairs
)

SELECT *
FROM with_distance
WHERE distance_km <= 10