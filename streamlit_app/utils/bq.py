"""BigQuery client and query runner.

Infrastructure
"""

import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account

PROJECT_ID = "air-quality-and-respiratory"
DATASET_MARTS = "air_quality_asthma_marts"

# Cap any single query at 100 MB. After aggregation in dbt these are tiny;
# if a query exceeds this, something is wrong and we want it to fail fast.
MAX_BYTES_BILLED = 100 * 1024 * 1024  # 100 MB


@st.cache_resource
def get_bigquery_client():
    """Single client shared across all sessions. cache_resource is the
     decorator for non-serialisable objects like DB clients."""
    try:
        if "gcp_service_account" in st.secrets:
            credentials = service_account.Credentials.from_service_account_info(
                st.secrets["gcp_service_account"],
                scopes=["https://www.googleapis.com/auth/bigquery"],
            )
            return bigquery.Client(project=PROJECT_ID, credentials=credentials)
    except FileNotFoundError:
        pass
    return bigquery.Client(project=PROJECT_ID)


def run_query(sql: str):
    """Run a query with a hard byte ceiling and return a dataframe."""
    client = get_bigquery_client()
    job_config = bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES_BILLED)
    return client.query(sql, job_config=job_config).to_dataframe()