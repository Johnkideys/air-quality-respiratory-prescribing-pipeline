WITH prescribing AS (
    SELECT *
    FROM {{ ref('stg_prescribing') }}
    WHERE is_negative_items = FALSE
      AND is_negative_actual_cost = FALSE
      AND is_incomplete_record = FALSE
),

practice_locations AS (
    SELECT *
    FROM {{ ref('stg_practice_locations') }}
),

practice_sensor_lookup AS (
    SELECT *
    FROM {{ ref('int_practice_sensor_lookup') }}
),

air_quality AS (
    SELECT *
    FROM {{ ref('int_monthly_air_quality') }}
),

-- Join prescribing to practice locations on practice_code for lat/lon
prescribing_with_location AS (
    SELECT
        p.*,
        pl.latitude                             AS practice_lat,
        pl.longitude                            AS practice_lon
    FROM prescribing p
    LEFT JOIN practice_locations pl
        ON p.practice_code = pl.practice_code
),

-- Join to practice_sensor_lookup to get eligible sensors per practice
prescribing_with_sensors AS (
    SELECT
        p.*,
        lkp.location_id,
        lkp.distance_km
    FROM prescribing_with_location p
    INNER JOIN practice_sensor_lookup lkp
        ON p.practice_code = lkp.practice_code
),

-- Join to air quality and average across all sensors within 10km
final AS (
    SELECT
        -- practice identifiers
        p.practice_code,
        p.row_name                              AS practice_name,
        p.ccg_code,
        p.practice_lat,
        p.practice_lon,

        -- time
        p.date                                  AS prescribing_month,

        -- prescribing classification
        p.bnf_section,
        p.bnf_label,

        -- prescribing measures
        -- SUM(p.items)                            AS total_items,
        -- SUM(p.quantity)                         AS total_quantity,
        -- SUM(p.actual_cost)                      AS total_actual_cost,

        ANY_VALUE(p.items)                      AS total_items,
        ANY_VALUE(p.quantity)                   AS total_quantity,
        ANY_VALUE(p.actual_cost)                AS total_actual_cost,

        -- air quality
        aq.pollutant,
        aq.unit,
        AVG(aq.avg_value)                       AS avg_air_quality_value,
        MIN(aq.avg_value)                       AS min_air_quality_value,
        MAX(aq.avg_value)                       AS max_air_quality_value,
        COUNT(DISTINCT aq.location_id)          AS num_sensors_averaged

    FROM prescribing_with_sensors p
    INNER JOIN air_quality aq
        ON p.location_id = aq.location_id
        AND p.date = aq.month
    GROUP BY
        p.practice_code,
        p.row_name,
        p.ccg_code,
        p.practice_lat,
        p.practice_lon,
        p.date,
        p.bnf_section,
        p.bnf_label,
        aq.pollutant,
        aq.unit
)

SELECT * FROM final