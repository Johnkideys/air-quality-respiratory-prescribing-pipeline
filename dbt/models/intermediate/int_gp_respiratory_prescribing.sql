{{ config(materialized='table') }}

WITH filtered AS (

    SELECT
        practice_code,
        row_name,
        ccg_code,
        date                            AS prescribing_month,
        bnf_section,
        bnf_label,
        items,
        quantity,
        actual_cost
    FROM {{ ref('stg_prescribing') }}
    WHERE setting = 4                          -- GP practices only
      AND bnf_section LIKE '03%'               -- BNF chapter 3 (Respiratory)
      AND is_negative_items = FALSE
      AND is_negative_actual_cost = FALSE
      AND is_incomplete_record = FALSE

)

SELECT * FROM filtered