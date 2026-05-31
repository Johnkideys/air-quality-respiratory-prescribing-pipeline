{{ config(materialized='table') }}

SELECT
    DATE_TRUNC(prescribing_month, MONTH) AS month,
    COUNT(*)                             AS row_count,
    SUM(items)                           AS total_items
FROM {{ ref('int_gp_respiratory_prescribing') }}
GROUP BY month
ORDER BY month