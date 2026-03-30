# =============================================================================
# terraform/variables.tf
# =============================================================================

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "europe-west2" # London area
}

variable "location" {
  description = "GCP location for BigQuery dataset"
  type = string
  default = "EU"
}