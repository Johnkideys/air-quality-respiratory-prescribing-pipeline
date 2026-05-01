WITH unique_sensor_locations AS (
    SELECT DISTINCT
        location_id,
        ANY_VALUE(latitude)     AS latitude,
        ANY_VALUE(longitude)    AS longitude
    FROM {{ ref('int_monthly_air_quality') }}
    WHERE latitude IS NOT NULL
      AND longitude IS NOT NULL
    GROUP BY location_id
),

practices AS (
    SELECT *
    FROM {{ ref('stg_practice_locations') }}
    WHERE latitude IS NOT NULL
      AND longitude IS NOT NULL
      AND TRIM(practice_name) != ''
),

haversine AS (
    SELECT
        p.practice_code,
        p.practice_name,
        p.latitude                              AS practice_lat,
        p.longitude                             AS practice_lon,
        s.location_id,
        s.latitude                              AS sensor_lat,
        s.longitude                             AS sensor_lon,
        (
            6371 * ACOS(
                COS(p.latitude * ACOS(-1)/180) * COS(s.latitude * ACOS(-1)/180)
                * COS((s.longitude * ACOS(-1)/180) - (p.longitude * ACOS(-1)/180))
                + SIN(p.latitude * ACOS(-1)/180) * SIN(s.latitude * ACOS(-1)/180)
            )
        )                                       AS distance_km
    FROM practices p
    INNER JOIN unique_sensor_locations s
        ON ABS(p.latitude - s.latitude) <= 0.09
        AND ABS(p.longitude - s.longitude) <= 0.13
)

SELECT *
FROM haversine
WHERE distance_km <= 10