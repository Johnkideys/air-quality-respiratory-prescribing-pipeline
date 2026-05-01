"""
Transform DAG: Load raw data from GCS into BigQuery.

Triggered by ingest_dag after new data lands in GCS.
Loads four tables into the `raw` BigQuery dataset, then (later) runs dbt.
"""

from datetime import datetime

from airflow.decorators import dag, task

PROJECT = "air-quality-and-respiratory"
DATASET = "raw"
BUCKET = "air-quality-and-respiratory-openaq-lake"


@dag(
    schedule=None,  # triggered by ingest_dag
    start_date=datetime(2026, 5, 1),
    catchup=False,
    tags=["transform"],
    doc_md=__doc__,
)
def transform_dag():

    @task
    def ensure_dataset():
        """Create the raw dataset if it doesn't exist."""
        from google.cloud import bigquery

        client = bigquery.Client(project=PROJECT)
        dataset_ref = bigquery.Dataset(f"{PROJECT}.{DATASET}")
        dataset_ref.location = "EU"
        client.create_dataset(dataset_ref, exists_ok=True)
        print(f"Dataset {PROJECT}.{DATASET} ready")

    @task
    def load_openaq_to_bq(**context):
        """Load one month of OpenAQ CSV.gz files from GCS into BigQuery."""
        from google.cloud import bigquery

        execution_date = context["logical_date"]
        year = execution_date.year
        month = execution_date.month

        client = bigquery.Client(project=PROJECT)
        table_id = f"{PROJECT}.{DATASET}.openaq_measurements"

        schema = [
            bigquery.SchemaField("location_id", "INTEGER"),
            bigquery.SchemaField("sensors_id", "INTEGER"),
            bigquery.SchemaField("location", "STRING"),
            bigquery.SchemaField("datetime", "TIMESTAMP"),
            bigquery.SchemaField("lat", "FLOAT64"),
            bigquery.SchemaField("lon", "FLOAT64"),
            bigquery.SchemaField("parameter", "STRING"),
            bigquery.SchemaField("units", "STRING"),
            bigquery.SchemaField("value", "FLOAT64"),
        ]

        table = bigquery.Table(table_id, schema=schema)
        table.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.MONTH,
            field="datetime",
        )
        client.create_table(table, exists_ok=True)

        # Idempotency: clear the target month before loading.
        # Rows that spill into adjacent months will land in THEIR partitions.
        delete_sql = f"""
            DELETE FROM `{table_id}`
            WHERE DATE_TRUNC(DATE(`datetime`), MONTH) = DATE '{year}-{month:02d}-01'
        """
        client.query(delete_sql).result()

        uri = f"gs://{BUCKET}/raw/openaq/year={year}/month={month:02d}/*.csv.gz"

        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=1,
            schema=schema,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        )

        job = client.load_table_from_uri(uri, table_id, job_config=job_config)
        result = job.result()
        print(f"Loaded {result.output_rows} OpenAQ rows (target month={year}-{month:02d})")
        return result.output_rows

    @task
    def load_prescribing_to_bq(**context):
        """Load one month of prescribing parquet from GCS into BigQuery.

        Two-step:
        1. Load parquet into a staging table (period_date is STRING in source).
        2. INSERT into the partitioned table with period_date cast to DATE.
        """
        from google.cloud import bigquery

        execution_date = context["logical_date"]
        year = execution_date.year
        month = execution_date.month

        client = bigquery.Client(project=PROJECT)
        table_id = f"{PROJECT}.{DATASET}.prescribing"
        staging_id = f"{PROJECT}.{DATASET}.prescribing_staging_{year}{month:02d}"

        # Final table schema — period_date and date cast to DATE
        schema = [
            bigquery.SchemaField("items", "INTEGER"),
            bigquery.SchemaField("quantity", "FLOAT64"),
            bigquery.SchemaField("actual_cost", "FLOAT64"),
            bigquery.SchemaField("date", "DATE"),
            bigquery.SchemaField("row_id", "STRING"),
            bigquery.SchemaField("row_name", "STRING"),
            bigquery.SchemaField("ccg", "STRING"),
            bigquery.SchemaField("setting", "INTEGER"),
            bigquery.SchemaField("bnf_section", "STRING"),
            bigquery.SchemaField("bnf_label", "STRING"),
            bigquery.SchemaField("period_date", "DATE"),
        ]

        # Ensure final partitioned table exists
        table = bigquery.Table(table_id, schema=schema)
        table.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.MONTH,
            field="period_date",
        )
        client.create_table(table, exists_ok=True)

        # --- Step 1: Load parquet into a temporary staging table ---
        uri = f"gs://{BUCKET}/raw/prescribing/year={year}/month={month:02d}/*.parquet"
        staging_job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.PARQUET,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        staging_job = client.load_table_from_uri(uri, staging_id, job_config=staging_job_config)
        staging_job.result()
        print(f"Staging loaded: {staging_job.output_rows} rows into {staging_id}")

        # --- Step 2: Clear target month, then INSERT from staging with casts ---
        delete_sql = f"""
            DELETE FROM `{table_id}`
            WHERE DATE_TRUNC(period_date, MONTH) = DATE '{year}-{month:02d}-01'
        """
        client.query(delete_sql).result()

        # Prescribing date strings are 'YYYYMMDD' — adjust format string if different.
        # (Check your data: PARSE_DATE('%Y%m%d', '20250101') works for '20250101'.
        #  If your strings look like '2025-01-01', use '%Y-%m-%d' instead.)
        insert_sql = f"""
            INSERT INTO `{table_id}` (
                items, quantity, actual_cost, date, row_id, row_name,
                ccg, setting, bnf_section, bnf_label, period_date
            )
            SELECT
                items,
                quantity,
                actual_cost,
                SAFE.PARSE_DATE('%Y-%m-%d', date) AS date,
                row_id,
                row_name,
                ccg,
                setting,
                bnf_section,
                bnf_label,
                SAFE.PARSE_DATE('%Y-%m-%d', period_date) AS period_date
            FROM `{staging_id}`
        """
        insert_job = client.query(insert_sql)
        insert_job.result()
        inserted = insert_job.num_dml_affected_rows
        print(f"Inserted {inserted} prescribing rows into partition {year}-{month:02d}")

        # --- Step 3: Drop the staging table ---
        client.delete_table(staging_id, not_found_ok=True)
        print(f"Dropped staging table {staging_id}")

        return inserted

    @task
    def load_practice_locations_to_bq():
        """Load practice locations parquet from GCS into BigQuery (full overwrite)."""
        from google.cloud import bigquery

        client = bigquery.Client(project=PROJECT)
        table_id = f"{PROJECT}.{DATASET}.practice_locations"
        uri = f"gs://{BUCKET}/raw/practice_locations/practice_locations.parquet"

        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.PARQUET,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )

        job = client.load_table_from_uri(uri, table_id, job_config=job_config)
        result = job.result()
        print(f"Loaded {result.output_rows} practice locations")
        return result.output_rows

    @task
    def load_uk_stations_to_bq():
        """Load UK station list CSV from GCS into BigQuery (full overwrite)."""
        from google.cloud import bigquery

        client = bigquery.Client(project=PROJECT)
        table_id = f"{PROJECT}.{DATASET}.uk_stations"
        uri = f"gs://{BUCKET}/config/uk_locations.csv"

        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=1,
            schema=[
                bigquery.SchemaField("location_id", "INTEGER"),
                bigquery.SchemaField("name", "STRING"),
                bigquery.SchemaField("latitude", "FLOAT64"),
                bigquery.SchemaField("longitude", "FLOAT64"),
                bigquery.SchemaField("is_monitor", "BOOLEAN"),
                bigquery.SchemaField("is_mobile", "BOOLEAN"),
                bigquery.SchemaField("has_pm25", "BOOLEAN"),
                bigquery.SchemaField("pm25_sensor_id", "INTEGER"),
                bigquery.SchemaField("has_pm10", "BOOLEAN"),
                bigquery.SchemaField("pm10_sensor_id", "INTEGER"),
                bigquery.SchemaField("has_no2", "BOOLEAN"),
                bigquery.SchemaField("no2_sensor_id", "INTEGER"),
            ],
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )

        job = client.load_table_from_uri(uri, table_id, job_config=job_config)
        result = job.result()
        print(f"Loaded {result.output_rows} UK stations")
        return result.output_rows

    @task
    def run_dbt():
        """Run dbt models to transform raw BigQuery tables into staging/marts."""
        import subprocess

        result = subprocess.run(
            ["dbt", "run", "--profiles-dir", "/opt/airflow/dbt", "--project-dir", "/opt/airflow/dbt"],
            capture_output=True,
            text=True,
        )
        print(result.stdout)
        if result.returncode != 0:
            print(result.stderr)
            raise Exception(f"dbt run failed with exit code {result.returncode}")

    # Ensure dataset (in BigQuery) exists first, then load all four tables in parallel, then run dbt
    ds = ensure_dataset()
    openaq = load_openaq_to_bq()
    prescribing = load_prescribing_to_bq()
    practice_locs = load_practice_locations_to_bq()
    stations = load_uk_stations_to_bq()
    dbt = run_dbt()

    ds >> [openaq, prescribing, practice_locs, stations] >> dbt


transform_dag()
