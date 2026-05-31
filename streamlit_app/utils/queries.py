"""Cached data loaders.

Every function that talks to BigQuery and returns a dataframe lives here.
Cache invalidates on app restart/redeploy (data refreshes monthly, so no TTL).
"""

import streamlit as st

from utils.bq import PROJECT_ID, DATASET_MARTS, run_query


# ==============================================================
# National-level loaders (Tab 2)
# ==============================================================

@st.cache_data
def load_national_prescription_data():
    return run_query(f"""
        SELECT
            prescribing_month,
            bnf_label,
            total_items,
            total_cost
        FROM `{PROJECT_ID}.{DATASET_MARTS}.mart_national_monthly_prescribing`
        ORDER BY prescribing_month
    """)


@st.cache_data
def load_national_air_quality():
    return run_query(f"""
        SELECT
            air_quality_month,
            pollutant,
            avg_air_quality,
            unit
        FROM `{PROJECT_ID}.{DATASET_MARTS}.mart_national_monthly_air_quality`
        ORDER BY air_quality_month
    """)


# ==============================================================
# Overview loaders (Tab 1)
# ==============================================================

@st.cache_data
def load_overview_metadata():
    summary = run_query(f"""
        SELECT * FROM `{PROJECT_ID}.{DATASET_MARTS}.mart_dashboard_overview`
    """).iloc[0]

    rx_monthly = run_query(f"""
        SELECT month, row_count, total_items
        FROM `{PROJECT_ID}.{DATASET_MARTS}.mart_overview_rx_monthly`
        ORDER BY month
    """)

    rx_bnf = run_query(f"""
        SELECT bnf_label, row_count, total_items
        FROM `{PROJECT_ID}.{DATASET_MARTS}.mart_overview_rx_bnf`
        ORDER BY total_items DESC
    """)

    aq_pollutant = run_query(f"""
        SELECT pollutant, reading_count, num_stations
        FROM `{PROJECT_ID}.{DATASET_MARTS}.mart_overview_aq_pollutant`
        ORDER BY reading_count DESC
    """)

    aq_coverage = run_query(f"""
        SELECT months_with_data, station_count, total_months
        FROM `{PROJECT_ID}.{DATASET_MARTS}.mart_overview_aq_coverage`
        ORDER BY months_with_data
    """)

    return {
        "summary": summary,
        "rx_monthly": rx_monthly,
        "rx_bnf": rx_bnf,
        "aq_pollutant": aq_pollutant,
        "aq_coverage": aq_coverage,
    }


# ==============================================================
# Practice-level loaders (Tab 3)
# ==============================================================

@st.cache_data
def load_practice_filters():
    ccgs = run_query(f"""
        SELECT DISTINCT ccg_code
        FROM `{PROJECT_ID}.{DATASET_MARTS}.mart_prescribing_air_quality`
        WHERE ccg_code IS NOT NULL
        ORDER BY ccg_code
    """)
    pollutants = run_query(f"""
        SELECT DISTINCT pollutant
        FROM `{PROJECT_ID}.{DATASET_MARTS}.mart_prescribing_air_quality`
        ORDER BY pollutant
    """)
    return ccgs, pollutants


@st.cache_data
def load_practices_for_ccg(ccg_code: str | None):
    where = f"WHERE ccg_code = '{ccg_code}'" if ccg_code and ccg_code != "All" else ""
    return run_query(f"""
        SELECT DISTINCT practice_code, practice_name
        FROM `{PROJECT_ID}.{DATASET_MARTS}.mart_prescribing_air_quality`
        {where}
        ORDER BY practice_name
    """)


@st.cache_data
def load_bnf_labels_for_practice(practice_code: str | None):
    where = f"WHERE practice_code = '{practice_code}'" if practice_code and practice_code != "All" else ""
    return run_query(f"""
        SELECT DISTINCT bnf_label
        FROM `{PROJECT_ID}.{DATASET_MARTS}.mart_prescribing_air_quality`
        {where}
        ORDER BY bnf_label
    """)


@st.cache_data
def load_practice_timeseries(
    practice_code: str | None,
    ccg_code: str | None,
    pollutant: str,
    bnf_labels: tuple,
):
    """Pull only the filtered slice. Uses tuple for bnf_labels so it's hashable."""
    if not bnf_labels:
        return None

    filters = [f"pollutant = '{pollutant}'"]
    if practice_code and practice_code != "All":
        filters.append(f"practice_code = '{practice_code}'")
    elif ccg_code and ccg_code != "All":
        filters.append(f"ccg_code = '{ccg_code}'")

    bnf_list = ", ".join(f"'{b}'" for b in bnf_labels)
    filters.append(f"bnf_label IN ({bnf_list})")

    where_clause = " AND ".join(filters)

    return run_query(f"""
        SELECT
            prescribing_month,
            SUM(total_items)             AS total_items,
            AVG(avg_air_quality_value)   AS avg_air_quality,
            ANY_VALUE(unit)              AS unit
        FROM `{PROJECT_ID}.{DATASET_MARTS}.mart_prescribing_air_quality`
        WHERE {where_clause}
        GROUP BY prescribing_month
        ORDER BY prescribing_month
    """)


# ==============================================================
# Correlation loaders (Tab 4)
# ==============================================================

@st.cache_data
def load_correlation_data(pollutant: str):
    return run_query(f"""
        SELECT
            practice_code,
            practice_name,
            ccg_code,
            prescribing_month,
            pollutant,
            unit,
            bnf_label,
            avg_air_quality_value,
            items_z_score,
            season
        FROM `{PROJECT_ID}.{DATASET_MARTS}.mart_practice_monthly_correlation`
        WHERE pollutant = '{pollutant}'
    """)


@st.cache_data
def load_available_pollutants():
    return run_query(f"""
        SELECT DISTINCT pollutant
        FROM `{PROJECT_ID}.{DATASET_MARTS}.mart_practice_monthly_correlation`
        ORDER BY pollutant
    """)["pollutant"].tolist()