"""
Air Quality & Respiratory Prescribing Dashboard

Visualises the relationship between air pollution levels and
respiratory prescribing across UK GP practices over time.
"""

import streamlit as st
import plotly.graph_objects as go
import numpy as np
from scipy import stats
from google.cloud import bigquery
from google.oauth2 import service_account

st.set_page_config(page_title="Air Quality & Prescribing", layout="wide")
st.title("Air Quality & Respiratory Prescribing")

PROJECT_ID = "air-quality-and-respiratory"


def get_bigquery_client():
    """Return a BigQuery client using Streamlit secrets if available, else local OAuth."""
    if "gcp_service_account" in st.secrets:
        credentials = service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"]
        )
        return bigquery.Client(project=PROJECT_ID, credentials=credentials)
    return bigquery.Client(project=PROJECT_ID)

DATASET_STAGING = "air_quality_asthma_staging"
DATASET_INTERMEDIATE = "air_quality_asthma_intermediate"
DATASET_MARTS = "air_quality_asthma_marts"


@st.cache_data(ttl=6000)
def load_national_prescription_data():
    """
    Loads prescription data from staging table and filters out 
    is_negative_items and is_incomplete_record.
    """    
    client = get_bigquery_client()
    query = f"""
        SELECT
            DATE_TRUNC(date, MONTH)             AS prescribing_month,
            bnf_label,
            SUM(items)                          AS total_items,
            SUM(actual_cost)                    AS total_cost
        FROM `{PROJECT_ID}.{DATASET_STAGING}.stg_prescribing`
        WHERE is_negative_items = FALSE
          AND is_incomplete_record = FALSE
        GROUP BY 1, 2
        ORDER BY 1
    """
    return client.query(query).to_dataframe()


@st.cache_data(ttl=6000)
def load_national_air_quality():
    """
    Loads air quality data from staging table.
    """  
    client = get_bigquery_client()
    query = f"""
        SELECT
            month                               AS air_quality_month,
            pollutant,
            AVG(avg_value)                      AS avg_air_quality,
            ANY_VALUE(unit)                     AS unit
        FROM `{PROJECT_ID}.{DATASET_INTERMEDIATE}.int_monthly_air_quality`
        GROUP BY 1, 2
        ORDER BY 1
    """
    return client.query(query).to_dataframe()


@st.cache_data(ttl=6000)
def load_mart_data():
    """
    Loading the final mart data. 
    """
    client = get_bigquery_client()
    query = f"""
        SELECT
            practice_code,
            practice_name,
            ccg_code,
            prescribing_month,
            bnf_section,
            bnf_label,
            pollutant,
            unit,
            total_items,
            total_actual_cost AS total_cost,
            avg_air_quality_value AS avg_air_quality
        FROM `{PROJECT_ID}.{DATASET_MARTS}.mart_prescribing_air_quality`
        ORDER BY prescribing_month
        """
    return client.query(query).to_dataframe()

@st.cache_data(ttl=6000)
def load_overview_metadata():
    """
    Loads small, aggregated metadata for the overview tab.
    Returns a dict of high-level counts and date ranges so
    we don't pull millions of rows just for headline metrics.
    """
    client = get_bigquery_client()

    # Prescribing summary
    rx_query = f"""
        SELECT
            MIN(date)                                AS min_date,
            MAX(date)                                AS max_date,
            COUNT(*)                                 AS total_rows,
            COUNT(DISTINCT CASE WHEN setting = 4 THEN practice_code END) AS num_gp_practices,
            COUNT(DISTINCT ccg_code)                 AS num_ccgs,
            COUNT(DISTINCT bnf_section)              AS num_bnf_sections,
            COUNT(DISTINCT bnf_label)                AS num_bnf_labels,
            SUM(CASE WHEN is_negative_items OR is_incomplete_record THEN 1 ELSE 0 END) AS excluded_rows
        FROM `{PROJECT_ID}.{DATASET_STAGING}.stg_prescribing`
        

    """

    # Per-month prescribing row counts
    rx_monthly_query = f"""
        SELECT
            DATE_TRUNC(date, MONTH) AS month,
            COUNT(*)                AS row_count
        FROM `{PROJECT_ID}.{DATASET_STAGING}.stg_prescribing`
        WHERE is_negative_items = FALSE
          AND is_incomplete_record = FALSE
        GROUP BY month
        ORDER BY month
    """

    # Prescribing by BNF label (was previously bnf_section)
    rx_bnf_query = f"""
        SELECT
            bnf_label,
            COUNT(*)         AS row_count,
            SUM(items)       AS total_items
        FROM `{PROJECT_ID}.{DATASET_STAGING}.stg_prescribing`
        WHERE is_negative_items = FALSE
        AND is_incomplete_record = FALSE
        GROUP BY bnf_label
        ORDER BY total_items DESC
    """

    # Air quality summary — adjust table/column names if yours differ
    aq_query = f"""
        SELECT
            MIN(month)                              AS min_month,
            MAX(month)                              AS max_month,
            COUNT(*)                                AS total_rows,
            COUNT(DISTINCT location_id)             AS num_stations,
            COUNT(DISTINCT pollutant)               AS num_pollutants
        FROM `{PROJECT_ID}.{DATASET_INTERMEDIATE}.int_monthly_air_quality`
    """

    # Air quality by pollutant
    aq_pollutant_query = f"""
        SELECT
            pollutant,
            COUNT(*)                       AS reading_count,
            COUNT(DISTINCT location_id)    AS num_stations
        FROM `{PROJECT_ID}.{DATASET_INTERMEDIATE}.int_monthly_air_quality`
        GROUP BY pollutant
        ORDER BY reading_count DESC
    """

    # Station coverage — how many months each station has data for
    aq_coverage_query = f"""
        WITH station_months AS (
            SELECT
                location_id,
                COUNT(DISTINCT month) AS months_with_data
            FROM `{PROJECT_ID}.{DATASET_INTERMEDIATE}.int_monthly_air_quality`
            GROUP BY location_id
        ),
        total_months AS (
            SELECT COUNT(DISTINCT month) AS total_months
            FROM `{PROJECT_ID}.{DATASET_INTERMEDIATE}.int_monthly_air_quality`
        )
        SELECT
            sm.months_with_data,
            COUNT(*) AS station_count,
            (SELECT total_months FROM total_months) AS total_months
        FROM station_months sm
        GROUP BY sm.months_with_data
        ORDER BY sm.months_with_data
    """

    return {
        "rx_summary": client.query(rx_query).to_dataframe().iloc[0],
        "rx_monthly": client.query(rx_monthly_query).to_dataframe(),
        "rx_bnf": client.query(rx_bnf_query).to_dataframe(),
        "aq_summary": client.query(aq_query).to_dataframe().iloc[0],
        "aq_pollutant": client.query(aq_pollutant_query).to_dataframe(),
        "aq_coverage": client.query(aq_coverage_query).to_dataframe(),
    }


# --- Tabs ---
tab1, tab2, tab3 = st.tabs([
    "📊 Overview of the Data",
    "🇬🇧 National Trends",
    "🏥 Practice Level Trends",
])

# ==============================================================
# TAB 1: Overview of the Data
# ==============================================================
with tab1:
    st.markdown("""
    This dashboard combines two open UK datasets to explore the relationship
    between **air quality** and **respiratory prescribing**:

    - **NHS Prescribing Data** — monthly prescription items dispensed by GP practices in England
    - **OpenAQ** — air quality readings from monitoring stations across the UK

    This tab gives a look at what's in each dataset before they're combined
    in later tabs.
    """)

    meta = load_overview_metadata()

    # ============================================================
    # PRESCRIBING SECTION
    # ============================================================
    st.header("💊 Prescribing dataset")

    rx = meta["rx_summary"]
    rx_monthly = meta["rx_monthly"]
    rx_bnf = meta["rx_bnf"]

    # Headline metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "Date range",
        f"{rx['min_date'].strftime('%b %Y')} – {rx['max_date'].strftime('%b %Y')}"
    )
    col2.metric("Total records", f"{rx['total_rows']:,}")
    col3.metric("GP practices", f"{rx['num_gp_practices']:,}")
    #col4.metric("CCGs", f"{rx['num_ccgs']:,}") # CCG number is 260 which isnt correct, in reality theres less than 50

    col1, col2, col3 = st.columns(3)
    col1.metric("BNF sections", f"{rx['num_bnf_sections']:,}")
    col2.metric("BNF labels", f"{rx['num_bnf_labels']:,}")
    excluded_pct = (rx["excluded_rows"] / rx["total_rows"] * 100) if rx["total_rows"] else 0
    col3.metric(
        "Records excluded",
        f"{rx['excluded_rows']:,}",
        delta=f"{excluded_pct:.2f}% of total",
        delta_color="off",
        help="Records flagged as having negative items or incomplete data, excluded from analysis.",
    )

    st.divider()

    # Records per month
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Records per month")
        rx_monthly["month_label"] = rx_monthly["month"].astype(str).str[:7]
        fig_rx_monthly = go.Figure()
        fig_rx_monthly.add_trace(go.Bar(
            x=rx_monthly["month_label"],
            y=rx_monthly["row_count"],
            marker_color="#636EFA",
        ))
        fig_rx_monthly.update_layout(
            xaxis=dict(title="Month", tickangle=-45, type="category"),
            yaxis=dict(title="Prescription records"),
            height=400,
            margin=dict(t=20),
        )
        st.plotly_chart(fig_rx_monthly, use_container_width=True)

    with col_right:
        st.subheader("Top BNF labels by total items")
        rx_bnf_top = rx_bnf.head(10)
        fig_rx_bnf = go.Figure()
        fig_rx_bnf.add_trace(go.Bar(
            x=rx_bnf_top["total_items"],
            y=rx_bnf_top["bnf_label"],
            orientation="h",
            marker_color="#636EFA",
        ))
        fig_rx_bnf.update_layout(
            xaxis=dict(title="Total prescription items"),
            yaxis=dict(title="", autorange="reversed"),
            height=400,
            margin=dict(t=20),
        )
        st.plotly_chart(fig_rx_bnf, use_container_width=True)

    st.divider()

    # ============================================================
    # AIR QUALITY SECTION
    # ============================================================
    st.header("🌬️ Air quality dataset")

    aq = meta["aq_summary"]
    aq_pollutant = meta["aq_pollutant"]
    aq_coverage = meta["aq_coverage"]

    # Headline metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "Date range",
        f"{str(aq['min_month'])[:7]} – {str(aq['max_month'])[:7]}"
    )
    col2.metric("Total readings", f"{aq['total_rows']:,}")
    col3.metric("Monitoring stations", f"{aq['num_stations']:,}")
    col4.metric("Pollutants tracked", f"{aq['num_pollutants']:,}")

    # Coverage breakdown
    if not aq_coverage.empty:
        #total_months = int(aq_coverage["total_months"].iloc[0])
        total_months_raw = aq_coverage["total_months"].iloc[0]
        if isinstance(total_months_raw, dict):
            total_months = int(total_months_raw["total_months"])
        else:
            total_months = int(total_months_raw)
        full_coverage = aq_coverage[aq_coverage["months_with_data"] == total_months]["station_count"].sum()
        partial_coverage = aq_coverage[aq_coverage["months_with_data"] < total_months]["station_count"].sum()

        col1, col2, col3 = st.columns(3)
        col1.metric(
            f"Stations with full coverage ({total_months} months)",
            f"{full_coverage:,}",
        )
        col2.metric(
            "Stations with partial coverage",
            f"{partial_coverage:,}",
        )
        if (full_coverage + partial_coverage) > 0:
            full_pct = full_coverage / (full_coverage + partial_coverage) * 100
            col3.metric(
                "Full-coverage %",
                f"{full_pct:.1f}%",
                help="Percentage of stations that reported readings in every month.",
            )

    st.divider()

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Readings by pollutant")
        fig_aq_pol = go.Figure()
        fig_aq_pol.add_trace(go.Bar(
            x=aq_pollutant["pollutant"],
            y=aq_pollutant["reading_count"],
            marker_color="#EF553B",
        ))
        fig_aq_pol.update_layout(
            xaxis=dict(title="Pollutant"),
            yaxis=dict(title="Number of monthly readings"),
            height=400,
            margin=dict(t=20),
        )
        st.plotly_chart(fig_aq_pol, use_container_width=True)

    with col_right:
        st.subheader("Station coverage distribution")
        fig_aq_cov = go.Figure()
        fig_aq_cov.add_trace(go.Bar(
            x=aq_coverage["months_with_data"],
            y=aq_coverage["station_count"],
            marker_color="#EF553B",
        ))
        fig_aq_cov.update_layout(
            xaxis=dict(title="Months of data per station"),
            yaxis=dict(title="Number of stations"),
            height=400,
            margin=dict(t=20),
        )
        st.plotly_chart(fig_aq_cov, use_container_width=True)

    st.divider()

    # ============================================================
    # METHODOLOGY EXPANDER
    # ============================================================
    with st.expander("ℹ️ About the data"):
        st.markdown("""
        **Prescribing data** comes from the NHS Business Services Authority's
        practice-level prescribing data, which records every prescription dispensed
        in England at GP practice level. We filter out records flagged as having
        negative items or incomplete data.

        **Air quality data** comes from OpenAQ, a global open air quality data
        platform. We aggregate raw readings to monthly averages per monitoring
        station before joining to prescribing data.

        **Linking the two:** in the "Practice Level Trends" tab, each GP practice is matched
        to all monitoring stations within 10km, and air quality readings are
        averaged across those stations. This is a coarse proxy for patient-level
        exposure but provides a reasonable approximation given the resolution
        of available data.
        """)

# ==============================================================
# TAB 2: National Trends by month
# ==============================================================
with tab2:
    st.markdown("""
    National view showing **all UK prescribing** and **all UK air quality sensors** data.
    """)

    df_rx = load_national_prescription_data()
    df_aq = load_national_air_quality()

    if df_rx.empty or df_aq.empty:
        st.warning("No national data available.")
        st.stop()

    # Sidebar filters for tab 1
    st.sidebar.header("National filters")

    pollutants = sorted(df_aq["pollutant"].dropna().unique())
    selected_pollutant = st.sidebar.selectbox("Pollutant", pollutants)

    bnf_labels = sorted(df_rx["bnf_label"].dropna().unique())
    selected_bnf = st.sidebar.multiselect("BNF categories", bnf_labels, default=bnf_labels)

    # Filter
    rx_filtered = df_rx[df_rx["bnf_label"].isin(selected_bnf)].copy()
    aq_filtered = df_aq[df_aq["pollutant"] == selected_pollutant].copy()

    # Aggregate prescribing across selected BNF categories
    rx_monthly = (
        rx_filtered
        .groupby("prescribing_month", as_index=False)
        .agg(total_items=("total_items", "sum"))
        .sort_values("prescribing_month")
    )
    rx_monthly["month_label"] = rx_monthly["prescribing_month"].astype(str).str[:7]
    aq_filtered["month_label"] = aq_filtered["air_quality_month"].astype(str).str[:7]

    # Merge on month
    merged = rx_monthly.merge(aq_filtered[["month_label", "avg_air_quality", "unit"]], on="month_label", how="inner")

    # Chart 1: Dual axis
    st.subheader(f"National Prescriptions vs {selected_pollutant}")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=merged["month_label"],
        y=merged["total_items"],
        name="Total prescription items",
        marker_color="#636EFA",
        yaxis="y",
    ))
    fig.add_trace(go.Scatter(
        x=merged["month_label"],
        y=merged["avg_air_quality"],
        name=f"Avg {selected_pollutant}",
        mode="lines+markers",
        marker_color="#EF553B",
        yaxis="y2",
    ))
    unit = merged["unit"].iloc[0] if not merged.empty else ""
    fig.update_layout(
        xaxis=dict(title="Month", tickangle=-45, type="category"),
        yaxis=dict(title="Prescription items", side="left"),
        yaxis2=dict(title=f"Avg {selected_pollutant} ({unit})", side="right", overlaying="y", rangemode="tozero"),
        legend=dict(orientation="h", y=1.12),
        height=500,
        margin=dict(t=60),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Chart 2: Prescribing by BNF category
    st.subheader("Prescriptions by BNF Category")
    fig2 = go.Figure()
    for label in selected_bnf:
        subset = df_rx[df_rx["bnf_label"] == label].copy()
        subset["month_label"] = subset["prescribing_month"].astype(str).str[:7]
        subset = subset.groupby("month_label", as_index=False).agg(total_items=("total_items", "sum"))
        fig2.add_trace(go.Scatter(
            x=subset["month_label"],
            y=subset["total_items"],
            name=label,
            mode="lines+markers",
        ))
    fig2.update_layout(
        xaxis=dict(title="Month", tickangle=-45, type="category"),
        yaxis=dict(title="Prescription items"),
        legend=dict(orientation="h", y=1.15),
        height=450,
        margin=dict(t=60),
    )
    st.plotly_chart(fig2, use_container_width=True)


# ==============================================================
# TAB 3: Practice Level
# ==============================================================
with tab3:
    st.markdown("""
    Practice-level view showing prescribing vs air quality for sensors **within 10km** of each practice.
    Filter by CCG or individual practice.
    """)

    df_practice = load_mart_data()

    if df_practice.empty:
        st.warning("No practice-level data available.")
        st.stop()

    st.sidebar.header("Practice filters")

    ccgs = sorted(df_practice["ccg_code"].dropna().unique())
    selected_ccg = st.sidebar.selectbox("CCG", ["All"] + list(ccgs))

    if selected_ccg != "All":
        df_practice = df_practice[df_practice["ccg_code"] == selected_ccg]

    practices = sorted(df_practice["practice_name"].dropna().unique())
    selected_practice = st.sidebar.selectbox("Practice", ["All"] + list(practices))

    if selected_practice != "All":
        df_practice = df_practice[df_practice["practice_name"] == selected_practice]

    pollutants_p = sorted(df_practice["pollutant"].dropna().unique())
    selected_pollutant_p = st.sidebar.selectbox("Pollutant ", pollutants_p)

    bnf_labels_p = sorted(df_practice["bnf_label"].dropna().unique())
    selected_bnf_p = st.sidebar.multiselect("BNF categories ", bnf_labels_p, default=bnf_labels_p)

    # Filter
    filtered_p = df_practice[
        (df_practice["pollutant"] == selected_pollutant_p) &
        (df_practice["bnf_label"].isin(selected_bnf_p))
    ].copy()

    if filtered_p.empty:
        st.info("No data for selected filters.")
        st.stop()

    # Aggregate
    monthly_p = (
        filtered_p
        .groupby("prescribing_month", as_index=False)
        .agg(
            total_items=("total_items", "sum"),
            avg_air_quality=("avg_air_quality", "mean")
        )
        .sort_values("prescribing_month")
    )
    monthly_p["month_label"] = monthly_p["prescribing_month"].astype(str).str[:7]

    unit_p = filtered_p["unit"].iloc[0] if not filtered_p.empty else ""

    st.subheader(f"Prescriptions vs {selected_pollutant_p} — {selected_practice if selected_practice != 'All' else selected_ccg if selected_ccg != 'All' else 'All practices with nearby sensors'}")

    fig3 = go.Figure()
    fig3.add_trace(go.Bar(
        x=monthly_p["month_label"],
        y=monthly_p["total_items"],
        name="Total prescription items",
        marker_color="#636EFA",
        yaxis="y",
    ))
    fig3.add_trace(go.Scatter(
        x=monthly_p["month_label"],
        y=monthly_p["avg_air_quality"],
        name=f"Avg {selected_pollutant_p}",
        mode="lines+markers",
        marker_color="#EF553B",
        yaxis="y2",
    ))
    fig3.update_layout(
        xaxis=dict(title="Month", tickangle=-45, type="category"),
        yaxis=dict(title="Prescription items", side="left"),
        yaxis2=dict(title=f"Avg {selected_pollutant_p} ({unit_p})", side="right", overlaying="y", rangemode="tozero"),
        legend=dict(orientation="h", y=1.12),
        height=500,
        margin=dict(t=60),
    )
    st.plotly_chart(fig3, use_container_width=True)
