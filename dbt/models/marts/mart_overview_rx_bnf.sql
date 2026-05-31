{{ config(materialized='table') }}

SELECT
    bnf_label,
    COUNT(*)    AS row_count,
    SUM(items)  AS total_items
FROM {{ ref('int_gp_respiratory_prescribing') }}
GROUP BY bnf_label
ORDER BY total_items DESC