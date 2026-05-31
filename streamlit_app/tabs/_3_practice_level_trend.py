"""Tab 3 — Practice-level trends.

Drill down to a single CCG or practice and see prescribing alongside
air quality from sensors within 10km.
"""

import streamlit as st
import plotly.graph_objects as go

from utils.queries import (
    load_practice_filters,
    load_practices_for_ccg,
    load_bnf_labels_for_practice,
    load_practice_timeseries,
)


def render():
    st.markdown("""
    Practice-level view. Pick a CCG and practice to see prescribing trends
    alongside air quality from sensors within 10km of that practice.
    """)

    ccgs_df, pollutants_df = load_practice_filters()

    st.subheader("Filters")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        ccg_options = ["All"] + ccgs_df["ccg_code"].tolist()
        selected_ccg = st.selectbox("CCG", ccg_options, key="tab3_ccg")

    with col2:
        practices_df = load_practices_for_ccg(selected_ccg)
        practice_options = ["All"] + practices_df["practice_name"].tolist()
        selected_practice_name = st.selectbox("Practice", practice_options, key="tab3_practice")

    with col3:
        selected_pollutant = st.selectbox(
            "Pollutant",
            pollutants_df["pollutant"].tolist(),
            key="tab3_pollutant",
        )

    # Resolve practice name back to code
    if selected_practice_name != "All":
        selected_practice_code = (
            practices_df.loc[practices_df["practice_name"] == selected_practice_name, "practice_code"]
            .iloc[0]
        )
    else:
        selected_practice_code = None

    bnf_df = load_bnf_labels_for_practice(selected_practice_code)
    bnf_labels = bnf_df["bnf_label"].tolist()

    default_bnf = [
        b for b in bnf_labels
        if any(kw in b.lower() for kw in ["bronchodilator", "beta", "salbutamol", "adrenoceptor"])
    ] or bnf_labels[:3]

    with col4:
        selected_bnf = st.multiselect(
            "BNF categories",
            bnf_labels,
            default=default_bnf,
            key="tab3_bnf",
        )

    if not selected_bnf:
        st.info("Select at least one BNF category above.")
        return

    monthly = load_practice_timeseries(
        selected_practice_code,
        selected_ccg,
        selected_pollutant,
        tuple(selected_bnf),
    )

    if monthly is None or monthly.empty:
        st.info("No data for selected filters.")
        return

    monthly["month_label"] = monthly["prescribing_month"].astype(str).str[:7]
    unit = monthly["unit"].iloc[0] if not monthly.empty else ""

    # Context line above the chart
    scope = "All practices in England"
    if selected_practice_name != "All":
        scope = selected_practice_name
    elif selected_ccg != "All":
        scope = f"CCG: {selected_ccg}"
    st.caption(f"Showing: **{scope}**")

    st.subheader(f"Prescriptions vs {selected_pollutant}")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=monthly["month_label"],
        y=monthly["total_items"],
        name="Total prescription items",
        marker_color="#636EFA",
        yaxis="y",
    ))
    fig.add_trace(go.Scatter(
        x=monthly["month_label"],
        y=monthly["avg_air_quality"],
        name=f"Avg {selected_pollutant}",
        mode="lines+markers",
        marker_color="#EF553B",
        yaxis="y2",
    ))
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