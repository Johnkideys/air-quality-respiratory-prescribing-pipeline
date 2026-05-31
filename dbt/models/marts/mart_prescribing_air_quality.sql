{{ config(
    materialized='table',
    partition_by={
        'field': 'prescribing_month',
        'data_type': 'date',
        'granularity': 'month'
    },
    cluster_by=['practice_code', 'pollutant', 'bnf_label']
) }}

WITH prescribing AS (

    -- Already filtered to GP practices + chapter 3 + quality flags
    SELECT
        practice_code,
        row_name,
        ccg_code,
        prescribing_month,
        bnf_section,
        bnf_label,
        items,
        quantity,
        actual_cost
    FROM {{ ref('int_gp_respiratory_prescribing') }}

),

practice_locations AS (
    SELECT
        practice_code,
        latitude    AS practice_lat,
        longitude   AS practice_lon
    FROM {{ ref('stg_practice_locations') }}
),

-- Aggregate air quality across all sensors near each practice FIRST,
-- so each practice gets exactly one air-quality value per pollutant per month.
-- This avoids the fan-out that broke the previous mart.
practice_monthly_air_quality AS (

    SELECT
        lkp.practice_code,
        aq.month                          AS air_quality_month,
        aq.pollutant,
        ANY_VALUE(aq.unit)                AS unit,
        AVG(aq.avg_value)                 AS avg_air_quality_value,
        MIN(aq.min_value)                 AS min_air_quality_value,
        MAX(aq.max_value)                 AS max_air_quality_value,
        COUNT(DISTINCT aq.location_id)    AS num_sensors_averaged,
        AVG(lkp.distance_km)              AS avg_sensor_distance_km
    FROM {{ ref('int_practice_sensor_lookup') }} lkp
    INNER JOIN {{ ref('int_monthly_air_quality') }} aq
        ON lkp.location_id = aq.location_id
    GROUP BY lkp.practice_code, aq.month, aq.pollutant

)

-- Now join cleanly: one prescribing row × one air-quality row per (practice, month, pollutant)
SELECT
    p.practice_code,
    p.row_name                              AS practice_name,
    p.ccg_code,
    pl.practice_lat,
    pl.practice_lon,

    p.prescribing_month,

    p.bnf_section,
    p.bnf_label,

    p.items                                 AS total_items,
    p.quantity                              AS total_quantity,
    p.actual_cost                           AS total_actual_cost,

    aq.pollutant,
    aq.unit,
    aq.avg_air_quality_value,
    aq.min_air_quality_value,
    aq.max_air_quality_value,
    aq.num_sensors_averaged,
    aq.avg_sensor_distance_km

FROM prescribing p
-- LEFT JOIN: enrich each prescribing row with the practice's lat/lon for
-- map display.

LEFT JOIN practice_locations pl
    ON p.practice_code = pl.practice_code
-- INNER JOIN: attach the practice's averaged nearby-sensor air quality for
-- that month. INNER (not LEFT) because a row with no nearby air quality
-- data has nothing to plot — drop these from the mart entirely.

INNER JOIN practice_monthly_air_quality aq
    ON p.practice_code = aq.practice_code
    AND p.prescribing_month = aq.air_quality_month