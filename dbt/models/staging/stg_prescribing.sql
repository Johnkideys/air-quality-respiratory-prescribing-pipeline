WITH source AS (
    SELECT * FROM {{ source('raw', 'prescribing') }}
),

renamed AS (
    SELECT
        -- identifiers
        row_id                                      AS practice_code,
        row_name,
        ccg                                         AS ccg_code,

        -- dates
        date,
        period_date,

        -- classification
        bnf_section,
        bnf_label,
        setting,

        -- measures
        items,
        quantity,
        actual_cost,

        -- data quality flags
        items < 0                                   AS is_negative_items,
        quantity < 0                                AS is_negative_quantity,
        actual_cost < 0                             AS is_negative_actual_cost,
        items = 0 AND quantity = 0                  AS is_zero_dispensing,
        actual_cost IS NULL OR items IS NULL
            OR quantity IS NULL                     AS is_incomplete_record

    FROM source
)

SELECT * FROM renamed