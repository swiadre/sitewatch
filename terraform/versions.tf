terraform {
  required_version = ">= 1.6"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.8"
    }
  }

  # state in a GCS bucket so CI and my laptop share it.
  # the bucket has to exist before `terraform init` (chicken and egg), I created it by hand:
  #   gcloud storage buckets create gs://<project>-tfstate --location=europe-central2
  backend "gcs" {
    prefix = "sitewatch"
    # bucket is passed with: terraform init -backend-config="bucket=<project>-tfstate"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
