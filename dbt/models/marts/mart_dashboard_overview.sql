{{ config(materialized='table') }}

WITH rx_summary AS (
    SELECT
        MIN(date)                   AS rx_min_date,
        MAX(date)                   AS rx_max_date,
        COUNT(*)                    AS rx_total_rows,
        COUNT(DISTINCT CASE WHEN setting = 4 THEN practice_code END) AS rx_num_gp_practices,
        COUNT(DISTINCT ccg_code)    AS rx_num_ccgs,
        COUNT(DISTINCT bnf_section) AS rx_num_bnf_sections,
        COUNT(DISTINCT bnf_label)   AS rx_num_bnf_labels,
        SUM(CASE WHEN is_negative_items OR is_incomplete_record THEN 1 ELSE 0 END) AS rx_excluded_rows
    FROM {{ ref('stg_prescribing') }}
),

aq_summary AS (
    SELECT 
        MIN(month)                   AS aq_min_month,
        MAX(month)                   AS aq_max_month,
        COUNT(*)                     AS aq_total_rows,
        COUNT(DISTINCT location_id)  AS aq_num_stations,
        COUNT(DISTINCT pollutant)    AS aq_num_pollutants
    FROM {{ ref('int_monthly_air_quality') }}
)

SELECT * FROM rx_summary CROSS JOIN aq_summary