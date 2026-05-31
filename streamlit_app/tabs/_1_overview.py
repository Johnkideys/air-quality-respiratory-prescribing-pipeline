"""Tab 1 — Overview of the data.

Snapshot of both source datasets (NHS prescribing + OpenAQ) before they're
combined in later tabs.
"""

import streamlit as st
import plotly.graph_objects as go

from utils.queries import load_overview_metadata


def render():
    st.markdown("""
    This dashboard combines two open UK datasets to explore the relationship
    between **air quality** and **respiratory prescribing**:

    - **NHS Prescribing Data** - monthly prescription items dispensed by GP practices in England
    - **OpenAQ** - air quality readings from monitoring stations across the UK

    This tab gives a look at what's in each dataset before they're combined
    in later tabs.
    """)

    meta = load_overview_metadata()
    rx = meta["summary"]
    rx_monthly = meta["rx_monthly"]
    rx_bnf = meta["rx_bnf"]
    aq_pollutant = meta["aq_pollutant"]
    aq_coverage = meta["aq_coverage"]

    # ==========================================================
    # Prescribing dataset
    # ==========================================================
    st.header("💊 Prescribing dataset")

    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Date range",
        f"{rx['rx_min_date'].strftime('%b %Y')} - {rx['rx_max_date'].strftime('%b %Y')}",
    )
    col2.metric("Total records", f"{rx['rx_total_rows']:,}")
    col3.metric("GP practices", f"{rx['rx_num_gp_practices']:,}")

    col1, col2, col3 = st.columns(3)
    col1.metric("BNF sections", f"{rx['rx_num_bnf_sections']:,}")
    col2.metric("BNF labels", f"{rx['rx_num_bnf_labels']:,}")
    excluded_pct = (rx["rx_excluded_rows"] / rx["rx_total_rows"] * 100) if rx["rx_total_rows"] else 0
    col3.metric(
        "Records excluded",
        f"{rx['rx_excluded_rows']:,}",
        delta=f"{excluded_pct:.2f}% of total",
        delta_color="off",
        help="Records flagged as having negative items or incomplete data, excluded from analysis.",
    )

    st.divider()

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Records per month")
        rx_monthly = rx_monthly.copy()
        rx_monthly["month_label"] = rx_monthly["month"].astype(str).str[:7]
        fig_rx_monthly = go.Figure()
        fig_rx_monthly.add_trace(go.Scatter(
        x=rx_monthly["month_label"],
        y=rx_monthly["total_items"],
        mode="lines+markers",
        line=dict(color="#636EFA"),
    ))
        fig_rx_monthly.update_layout(
            xaxis=dict(title="Month", tickangle=-45, type="category"),
            yaxis=dict(title="Prescription records"),
            height=400,
            margin=dict(t=20),
        )
        st.plotly_chart(fig_rx_monthly, use_container_width=True)

    with col_right:
        st.subheader("BNF labels by record count")
        rx_bnf_top = rx_bnf.head(10).sort_values("row_count")
        fig_rx_bnf = go.Figure()
        fig_rx_bnf.add_trace(go.Scatter(
            x=rx_bnf_top["total_items"],
            y=rx_bnf_top["bnf_label"],
            mode="markers",
            marker=dict(color="#636EFA", size=12),
        ))
        fig_rx_bnf.update_layout(
            xaxis=dict(title="Prescription records"),  # autoscales, no forced zero
            yaxis=dict(title=""),
            height=400,
            margin=dict(t=20),
        )
        st.plotly_chart(fig_rx_bnf, use_container_width=True)

    st.divider()

    # ==========================================================
    # Air quality dataset
    # ==========================================================
    st.header("🌬️ Air quality dataset")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "Date range",
        f"{str(rx['aq_min_month'])[:7]} - {str(rx['aq_max_month'])[:7]}",
    )
    col2.metric("Total readings", f"{rx['aq_total_rows']:,}")
    col3.metric("Monitoring stations", f"{rx['aq_num_stations']:,}")
    col4.metric("Pollutants tracked", f"{rx['aq_num_pollutants']:,}")

    if not aq_coverage.empty:
        total_months = int(aq_coverage["total_months"].iloc[0])
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

    with st.expander("About the data"):
        st.markdown("""
        **Prescribing data** comes from the NHS Business Services Authority's
        practice-level prescribing data, which records every prescription dispensed
        in England at GP practice level. We filter out records flagged as having
        negative items or incomplete data, and restrict to GP practices
        (NHS Digital setting code 4) and BNF chapter 3 (respiratory system).

        **Air quality data** comes from OpenAQ, a global open air quality data
        platform. We aggregate raw readings to monthly averages per monitoring
        station before joining to prescribing data, and restrict to pollutants
        relevant to respiratory health (PM2.5, PM10, NO₂, O₃, SO₂).

        **Linking the two:** in the "Practice Level Trends" tab, each GP practice is
        matched to all monitoring stations within 10km, and air quality readings
        are averaged across those stations. This is a coarse proxy for patient-level
        exposure but provides a reasonable approximation given the resolution of
        available data.
        """)