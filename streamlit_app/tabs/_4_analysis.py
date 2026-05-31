"""Tab 4 — Pollution vs prescribing correlation.

Scatter plot of (practice, month) combinations comparing within-practice
z-scored bronchodilator prescribing against local pollutant levels.
"""

import streamlit as st
import plotly.express as px
from scipy import stats

from utils.queries import load_correlation_data, load_available_pollutants


def render():
    st.header("🔍 Does air pollution predict respiratory prescribing?")

    st.markdown("""
    The medical literature consistently links short-term spikes in pollutants
    like **PM2.5** and **NO₂** to increased use of **short-acting beta-2
    agonists (SABAs)** — the rescue inhalers used to treat asthma exacerbations.

    Can we see this relationship in open UK data? Below is a scatter plot
    of **thousands of (GP practice, month) combinations**, comparing each
    practice's bronchodilator prescribing to the air quality measured by
    sensors within 10km of that practice.
    """)

    # ---- Filters
    col_pollutant, col_season = st.columns([1, 2])

    with col_pollutant:
        pollutants = load_available_pollutants()
        selected_pollutant = st.selectbox(
            "Pollutant",
            pollutants,
            index=pollutants.index("pm25") if "pm25" in pollutants else 0,
            key="corr_pollutant",
        )
    
    with col_season:
        all_seasons = ["Spring", "Summer", "Autumn", "Winter"]
        selected_seasons = st.multiselect(
            "Seasons (filter to isolate seasonal confounding)",
            all_seasons,
            default=all_seasons,
            key="corr_seasons",
            help="Pollution and prescribing both vary seasonally. Filter to "
                 "specific seasons to see if the correlation survives within them.",
        )

    df = load_correlation_data(selected_pollutant)
    df_all = df.copy() # This is for the expander where I show season correlations in a table
    if df.empty:
        st.warning("No data for that pollutant.")
        return
    
    # ---- Apply season filter
    if not selected_seasons:
        st.warning("Select at least one season.")
        return

    df = df[df["season"].isin(selected_seasons)]

    if len(df) < 3:
        st.warning("Not enough data points after filtering.")
        return

    # Show what's being analyzed
    if len(selected_seasons) < 4:
        st.info(
            f"Showing **{', '.join(selected_seasons)}** only "
            f"({len(df):,} data points). Compare to all-season result by "
            f"selecting all four seasons."
        )


    # ---- Correlations
    pearson_r, pearson_p = stats.pearsonr(df["avg_air_quality_value"], df["items_z_score"])
    spearman_r, spearman_p = stats.spearmanr(df["avg_air_quality_value"], df["items_z_score"])

    col1, col2, col3 = st.columns(3)
    col1.metric("Data points", f"{len(df):,}")
    col2.metric(
        "Pearson r",
        f"{pearson_r:.3f}",
        # delta=f"p = {pearson_p:.2e}",
        # delta_color="off",
        help="Linear correlation. Range -1 to +1. Closer to 0 means weaker.",
    )
    col2.caption(f"p = {pearson_p:.2e}")

    col3.metric(
        "Spearman ρ",
        f"{spearman_r:.3f}",
        delta=f"p = {spearman_p:.2e}",
        delta_color="off",
        help="Rank-based correlation, robust to outliers.",
    )

    # ---- Scatter
    fig = px.scatter(
        df,
        x="avg_air_quality_value",
        y="items_z_score",
        color="season",
        opacity=0.4,
        trendline="ols",
        trendline_scope="overall",
        labels={
            "avg_air_quality_value": f"Avg {selected_pollutant} ({df['unit'].iloc[0]})",
            "items_z_score": "Within-practice z-score of bronchodilator items",
            "season": "Season",
        },
        height=600,
        hover_data=["practice_name", "ccg_code", "prescribing_month"],
        color_discrete_map={
            "Winter": "#1f77b4",
            "Spring": "#2ca02c",
            "Summer": "#ff7f0e",
            "Autumn": "#d62728",
        },
        category_orders={"season": ["Spring", "Summer", "Autumn", "Winter"]},
    )
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
    fig.update_layout(legend=dict(orientation="h", y=1.05))
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Compare correlations across all seasons"):
        season_stats = []
        for season in ["Spring", "Summer", "Autumn", "Winter"]:
            season_df = df_all[df_all["season"] == season]  # df_all = unfiltered
            if len(season_df) >= 3:
                r, p = stats.pearsonr(
                    season_df["avg_air_quality_value"], 
                    season_df["items_z_score"]
                )
                season_stats.append({
                    "Season": season,
                    "n": f"{len(season_df):,}",
                    "Pearson r": f"{r:.3f}",
                    "p-value": f"{p:.2e}",
                })
        
        st.dataframe(season_stats, hide_index=True)

    # ---- Reader guide
    with st.expander("📖 How to read this chart"):
        st.markdown("""
        - Each **dot** is one GP practice in one month
        - **X-axis**: average air pollution that month near that practice
        - **Y-axis**: how unusual that month's prescribing was *for that
          specific practice*. 0 = average; +1 = one standard deviation
          above what they normally do; -1 = one below
        - **Colour**: season — lets you check whether any correlation
          survives *within* a season or is just shared seasonality
        - **Trend line**: best-fit straight line across all dots. If it
          slopes up, higher pollution months tend to coincide with
          above-average prescribing

        **Why z-scores?** Big-city practices prescribe far more in absolute
        terms than rural ones, mostly because they have more patients.
        Comparing each practice to its own historical average controls
        for practice size, demographics, and regional differences in a
        single step — leaving only the question of "is this month unusual
        for *this* practice?"
        """)

    # ---- Interpretation
    if abs(pearson_r) < 0.1:
        verdict = "very weak"
    elif abs(pearson_r) < 0.3:
        verdict = "weak"
    elif abs(pearson_r) < 0.5:
        verdict = "moderate"
    else:
        verdict = "strong"

    direction = "positive" if pearson_r > 0 else "negative"
    significance = "statistically significant" if pearson_p < 0.05 else "not statistically significant"

    st.markdown(f"""
    ### Interpretation

    The correlation is **{verdict}** and **{direction}** (r = {pearson_r:.3f}),
    and **{significance}** (p = {pearson_p:.2e}).

    With {len(df):,} data points, even tiny true correlations produce statistical
    significance — so the size of `r` matters more than the p-value here.
    A real, practically meaningful effect would show r ≥ 0.2 or so.
    """)

    with st.expander("⚠️ What this analysis cannot show"):
        st.markdown("""
        - **Confounders not controlled**: deprivation, smoking rates, age
          distribution, indoor air quality, and temperature are correlated
          with both pollution exposure and respiratory prescribing
        - **Spatial proxy is coarse**: we average air quality across sensors
          within 10km; actual patient exposure varies enormously by
          micro-location, time spent outdoors, occupation
        - **Monthly granularity**: a 3-day pollution inversion may cause a
          SABA spike that disappears when averaged into a monthly mean
        - **Prescribing ≠ symptoms**: patients use existing inhalers; not
          every symptom increase produces a new prescription
        - **Z-score baseline is the whole period**: includes any pollution
          effect itself, slightly attenuating the correlation

        This is exploratory analysis, not a medical study.
        """)