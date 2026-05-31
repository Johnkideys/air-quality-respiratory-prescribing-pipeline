{{ config(
    materialized='table',
    partition_by={
        'field': 'air_quality_month',
        'data_type': 'date',
        'granularity': 'month'
    },
    cluster_by=['pollutant']
) }}

SELECT
    month                       AS air_quality_month,
    pollutant,
    ANY_VALUE(unit)             AS unit,
    AVG(avg_value)              AS avg_air_quality,
    MIN(min_value)              AS min_air_quality,
    MAX(max_value)              AS max_air_quality,
    SUM(reading_count)          AS reading_count,
    AVG(days_with_data)         AS avg_days_with_data,
    COUNT(DISTINCT location_id) AS num_stations
FROM {{ ref('int_monthly_air_quality') }}
GROUP BY month, pollutant