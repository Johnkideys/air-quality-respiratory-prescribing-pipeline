"""
Air Quality & Respiratory Prescribing Dashboard
"""

import streamlit as st

from tabs import _1_overview, _2_national_trend, _3_practice_level_trend, _4_analysis

st.set_page_config(page_title="Air Quality & Prescribing", layout="wide")
st.title("Air Quality & Respiratory Prescribing")

with st.sidebar:
    st.markdown("### About")
    st.markdown("""
    Combining NHS prescribing data with OpenAQ air quality 
    to explore the relationship between pollution and respiratory care.
    
    **Sources**
    - NHSBSA monthly prescribing
    - OpenAQ UK stations
    
    **Stack**
    - dbt + BigQuery + Streamlit
    
    [📂 GitHub](https://github.com/Johnkideys/air-quality-respiratory-prescribing-pipeline)  
    """)

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Overview of the Data",
    "🇬🇧 National Trends",
    "🏥 Practice Level Trends",
    "🔍 Pollution vs Prescribing Analysis",
])

with tab1:
    _1_overview.render()

with tab2:
    _2_national_trend.render()

with tab3:
    _3_practice_level_trend.render()

with tab4:
    _4_analysis.render()