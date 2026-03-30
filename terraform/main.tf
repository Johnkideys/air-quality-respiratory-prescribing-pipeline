# =============================================================================
# terraform/main.tf
# =============================================================================

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# --- Data Lake (GCS) ---
resource "google_storage_bucket" "data_lake" {
  name          = "${var.project_id}-openaq-lake"
  location      = var.region
  # force_destroy = true # allows terraform destroy to remove non empty bucket
  storage_class = "STANDARD"
}

# --- Data Warehouse (BigQuery) ---
resource "google_bigquery_dataset" "openaq_data" {
  dataset_id = "openaq_data"
  location   = var.location

  description = "Air quality and prescribing data for DE zoomcamp project"

  # delete_contents_on_destroy = true # allows terraform destroy to remove tables
}
