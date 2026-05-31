"""Tab 2 — National trends.

Aggregate prescribing across all of England against national average
pollutant levels. Lets the user pick which pollutant and which BNF
categories to compare.
"""

import streamlit as st
import plotly.graph_objects as go

from utils.queries import load_national_prescription_data, load_national_air_quality


def render():
    st.markdown("""
    National view showing **all UK prescribing** and **all UK air quality sensors** data.
    """)

    df_rx = load_national_prescription_data()
    df_aq = load_national_air_quality()

    if df_rx.empty or df_aq.empty:
        st.warning("No national data available.")
        return

    # ---- Filters
    col1, col2 = st.columns([1, 2])
    with col1:
        pollutants = sorted(df_aq["pollutant"].dropna().unique())
        selected_pollutant = st.selectbox("Pollutant", pollutants, key="tab2_pollutant")
    with col2:
        bnf_labels = sorted(df_rx["bnf_label"].dropna().unique())
        default_bnf = [
            b for b in bnf_labels
            if any(kw in b.lower() for kw in ["bronchodilator", "beta", "salbutamol", "adrenoceptor"])
        ] or bnf_labels[:3]
        selected_bnf = st.multiselect(
            "BNF categories",
            bnf_labels,
            default=default_bnf,
            key="tab2_bnf",
        )

    if not selected_bnf:
        st.info("Select at least one BNF category above.")
        return

    # ---- Aggregate
    rx_filtered = df_rx[df_rx["bnf_label"].isin(selected_bnf)].copy()
    aq_filtered = df_aq[df_aq["pollutant"] == selected_pollutant].copy()

    rx_monthly = (
        rx_filtered
        .groupby("prescribing_month", as_index=False)
        .agg(total_items=("total_items", "sum"))
        .sort_values("prescribing_month")
    )
    rx_monthly["month_label"] = rx_monthly["prescribing_month"].astype(str).str[:7]
    aq_filtered["month_label"] = aq_filtered["air_quality_month"].astype(str).str[:7]

    merged = rx_monthly.merge(
        aq_filtered[["month_label", "avg_air_quality", "unit"]],
        on="month_label",
        how="inner",
    )

    # ---- Chart 1: dual-axis prescribing vs pollutant
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
        yaxis2=dict(
            title=f"Avg {selected_pollutant} ({unit})",
            side="right",
            overlaying="y",
            rangemode="tozero",
        ),
        legend=dict(orientation="h", y=1.12),
        height=500,
        margin=dict(t=60),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ---- Chart 2: per-BNF lines
    st.subheader("Prescriptions by BNF Category")
    fig2 = go.Figure()
    for label in selected_bnf:
        subset = df_rx[df_rx["bnf_label"] == label].copy()
        subset["month_label"] = subset["prescribing_month"].astype(str).str[:7]
        subset = (
            subset
            .groupby("month_label", as_index=False)
            .agg(total_items=("total_items", "sum"))
        )
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