variable "project_id" {
  description = "GCP project id"
  type        = string
}

variable "region" {
  description = "Main region (Warsaw, close to the users of the sites)"
  type        = string
  default     = "europe-central2"
}

variable "zone" {
  type    = string
  default = "europe-central2-a"
}

variable "machine_type" {
  description = "Main VM runs prometheus + grafana + alertmanager + prober, e2-micro (1GB) is too small"
  type        = string
  default     = "e2-small"
}

variable "probe_regions" {
  description = "Extra regions with only a prober, to tell 'site is down' from 'my network is down'"
  type        = map(string) # region => zone
  default = {
    "europe-west1" = "europe-west1-b" # Belgium
    "us-central1"  = "us-central1-a"  # Iowa
  }
}

variable "admin_cidrs" {
  description = "IPs allowed to SSH and open Grafana (my home IP), e.g. [\"1.2.3.4/32\"]"
  type        = list(string)
}

variable "repo_url" {
  type    = string
  default = "https://github.com/swiadre/sitewatch.git"
}

variable "dns_zone" {
  description = "Optional: name of a Cloud DNS managed zone, creates monitoring.<domain>. Empty = skip"
  type        = string
  default     = ""
}

variable "dns_name" {
  description = "e.g. monitoring.example.com. (with the dot at the end)"
  type        = string
  default     = ""
}
