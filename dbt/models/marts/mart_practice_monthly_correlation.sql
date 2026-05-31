{{ config(
    materialized='table',
    partition_by={
        'field': 'prescribing_month',
        'data_type': 'date',
        'granularity': 'month'
    },
    cluster_by=['pollutant', 'bnf_label']
) }}

-- One row per practice × month × pollutant × bnf_label, with the
-- prescribing count z-scored within each (practice, bnf_label) so
-- the value represents 'how unusual is this month for this practice
-- on this drug type'. Used by the correlation analysis tab.

WITH base AS (

    SELECT
        practice_code,
        practice_name,
        ccg_code,
        prescribing_month,
        pollutant,
        unit,
        bnf_section,
        bnf_label,
        total_items,
        avg_air_quality_value
    FROM {{ ref('mart_prescribing_air_quality') }}
    WHERE bnf_section LIKE '0301%'   -- bronchodilators only (BNF 3.1)

),

with_practice_stats AS (

    -- Compute each practice's own historical mean and stddev for that
    -- bnf_label, used as the per-practice baseline for the z-score.
    SELECT
        *,
        AVG(total_items)
            OVER (PARTITION BY practice_code, bnf_label) AS practice_mean_items,
        STDDEV(total_items)
            OVER (PARTITION BY practice_code, bnf_label) AS practice_std_items,
        COUNT(*)
            OVER (PARTITION BY practice_code, bnf_label) AS practice_n_months
    FROM base

),

final AS (

    SELECT
        practice_code,
        practice_name,
        ccg_code,
        prescribing_month,
        pollutant,
        unit,
        bnf_section,
        bnf_label,
        total_items,
        avg_air_quality_value,

        practice_mean_items,
        practice_std_items,
        practice_n_months,

        -- The z-score: 'how many std devs above/below this practice's
        -- own normal is this month's prescribing?'
        -- NULL when a practice has only one month of data (no variation
        -- to compute stddev from).
        SAFE_DIVIDE(total_items - practice_mean_items, practice_std_items)
            AS items_z_score,

        -- Season label for colour-coding the scatter plot.
        -- Lets us check whether any correlation survives within a season,
        -- or is just driven by shared winter/summer co-movement.
        CASE
            WHEN EXTRACT(MONTH FROM prescribing_month) IN (12, 1, 2)  THEN 'Winter'
            WHEN EXTRACT(MONTH FROM prescribing_month) IN (3, 4, 5)   THEN 'Spring'
            WHEN EXTRACT(MONTH FROM prescribing_month) IN (6, 7, 8)   THEN 'Summer'
            WHEN EXTRACT(MONTH FROM prescribing_month) IN (9, 10, 11) THEN 'Autumn'
        END                                                            AS season

    FROM with_practice_stats

)

SELECT *
FROM final
-- Drop practices with too few months of data to compute meaningful stats
WHERE practice_n_months >= 6
  AND items_z_score IS NOT NULL