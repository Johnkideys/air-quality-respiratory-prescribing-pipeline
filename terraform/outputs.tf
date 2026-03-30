# =============================================================================
# terraform/outputs.tf
# =============================================================================

output "data_lake_bucket" {
  description = "GCS bucket name for raw data"
  value       = google_storage_bucket.data_lake.name
}

output "bigquery_dataset" {
  description = "BigQuery dataset ID"
  value       = google_bigquery_dataset.openaq_data.dataset_id
}
