{{ config(
    materialized='table',
    partition_by={
        'field': 'prescribing_month',
        'data_type': 'date',
        'granularity': 'month'
    },
    cluster_by=['bnf_label']
) }}

SELECT
    prescribing_month,
    bnf_section,
    bnf_label,
    SUM(items)              AS total_items,
    SUM(quantity)           AS total_quantity,
    SUM(actual_cost)        AS total_cost,
    COUNT(DISTINCT practice_code) AS num_practices
FROM {{ ref('int_gp_respiratory_prescribing') }}
GROUP BY prescribing_month, bnf_section, bnf_label