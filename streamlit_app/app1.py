"""
Air Quality & Respiratory Prescribing Dashboard

Visualises the relationship between air pollution levels and
respiratory prescribing across UK GP practices over time.
"""

import streamlit as st
import plotly.graph_objects as go
from google.cloud import bigquery

st.set_page_config(page_title="Air Quality & Prescribing", layout="wide")
st.title("Air Quality & Respiratory Prescribing")

PROJECT_ID = "air-quality-and-respiratory"
DATASET_STAGING = "air_quality_asthma_staging"
DATASET_INTERMEDIATE = "air_quality_asthma_intermediate"
DATASET_MARTS = "air_quality_asthma_marts"


@st.cache_data(ttl=6000)
def load_national_data():
    client = bigquery.Client(project=PROJECT_ID)
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
    client = bigquery.Client(project=PROJECT_ID)
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
def load_practice_data():
    client = bigquery.Client(project=PROJECT_ID)
    query = f"""
        SELECT
            practice_code,
            practice_name,
            ccg_code,
            prescribing_month,
            bnf_label,
            pollutant,
            unit,
            ANY_VALUE(total_items)              AS total_items,
            ANY_VALUE(total_actual_cost)        AS total_cost,
            AVG(avg_air_quality_value)          AS avg_air_quality
        FROM `{PROJECT_ID}.{DATASET_MARTS}.mart_prescribing_air_quality`
        GROUP BY 1, 2, 3, 4, 5, 6, 7
        ORDER BY 4
    """
    return client.query(query).to_dataframe()


# --- Load data ---
tab1, tab2 = st.tabs(["🇬🇧 National Overview", "🏥 Practice Level"])


# ==============================================================
# TAB 1: National Overview
# ==============================================================
with tab1:
    st.markdown("""
    National view showing **all UK prescribing** vs **all UK air quality sensors** over time.
    No proximity filter applied — this shows the broad national trend.
    """)

    df_rx = load_national_data()
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

    # Summary stats
    with st.expander("Summary statistics"):
        col1, col2, col3 = st.columns(3)
        col1.metric("Months covered", rx_monthly["month_label"].nunique())
        col2.metric("Total prescription items", f"{rx_monthly['total_items'].sum():,.0f}")
        col3.metric(f"Avg {selected_pollutant}", f"{aq_filtered['avg_air_quality'].mean():.2f} {unit}")


# ==============================================================
# TAB 2: Practice Level
# ==============================================================
with tab2:
    st.markdown("""
    Practice-level view showing prescribing vs air quality for sensors **within 10km** of each practice.
    Filter by CCG or individual practice.
    """)

    df_practice = load_practice_data()

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

    with st.expander("Summary statistics"):
        col1, col2, col3 = st.columns(3)
        col1.metric("Practices", df_practice["practice_name"].nunique())
        col2.metric("Total prescription items", f"{monthly_p['total_items'].sum():,.0f}")
        col3.metric(f"Avg {selected_pollutant_p}", f"{monthly_p['avg_air_quality'].mean():.2f} {unit_p}")