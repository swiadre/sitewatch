locals {
  labels = { app = "sitewatch", managed_by = "terraform" }
}

# ---------- network ----------

resource "google_compute_network" "sitewatch" {
  name                    = "sitewatch"
  auto_create_subnetworks = true
}

# by default GCP denies all incoming traffic on a custom network, so only these get in
resource "google_compute_firewall" "admin" {
  name          = "sitewatch-admin"
  network       = google_compute_network.sitewatch.name
  source_ranges = var.admin_cidrs
  target_tags   = ["sitewatch-main"]

  allow {
    protocol = "tcp"
    ports    = ["22", "3000"] # ssh + grafana
  }
}

# main VM scrapes the regional probers on :8000
resource "google_compute_firewall" "scrape_probers" {
  name        = "sitewatch-scrape-probers"
  network     = google_compute_network.sitewatch.name
  source_tags = ["sitewatch-main"]
  target_tags = ["sitewatch-prober"]

  allow {
    protocol = "tcp"
    ports    = ["8000"]
  }
}

resource "google_compute_firewall" "iap_ssh" {
  # SSH through Identity-Aware Proxy (gcloud compute ssh --tunnel-through-iap) for all VMs
  name          = "sitewatch-iap-ssh"
  network       = google_compute_network.sitewatch.name
  source_ranges = ["35.235.240.0/20"]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

# ---------- service account (no default compute SA with editor role) ----------

resource "google_service_account" "sitewatch" {
  account_id   = "sitewatch-vm"
  display_name = "sitewatch VMs"
}

resource "google_project_iam_member" "logs" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.sitewatch.email}"
}

# ---------- main VM ----------

resource "google_compute_address" "main" {
  name   = "sitewatch-main"
  region = var.region
}

resource "google_compute_instance" "main" {
  name         = "sitewatch-main"
  machine_type = var.machine_type
  zone         = var.zone
  tags         = ["sitewatch-main"]
  labels       = local.labels

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 20
    }
  }

  network_interface {
    network = google_compute_network.sitewatch.id
    access_config {
      nat_ip = google_compute_address.main.address
    }
  }

  service_account {
    email  = google_service_account.sitewatch.email
    scopes = ["cloud-platform"]
  }

  metadata = {
    enable-oslogin = "TRUE"
  }

  metadata_startup_script = templatefile("${path.module}/startup-main.sh", {
    repo_url = var.repo_url
    probers = jsonencode([for r, vm in google_compute_instance.prober : {
      targets = ["${vm.network_interface[0].network_ip}:8000"]
      labels  = { region = r }
    }])
  })

  allow_stopping_for_update = true
}

# ---------- regional probers ----------

resource "google_compute_instance" "prober" {
  for_each = var.probe_regions

  name         = "sitewatch-prober-${each.key}"
  machine_type = "e2-micro" # only runs the prober, 1GB is plenty
  zone         = each.value
  tags         = ["sitewatch-prober"]
  labels       = merge(local.labels, { region = each.key })

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 10
    }
  }

  network_interface {
    network = google_compute_network.sitewatch.id
    access_config {} # ephemeral public IP, needed to reach the sites
  }

  service_account {
    email  = google_service_account.sitewatch.email
    scopes = ["cloud-platform"]
  }

  metadata = {
    enable-oslogin = "TRUE"
  }

  metadata_startup_script = templatefile("${path.module}/startup-prober.sh", {
    repo_url = var.repo_url
  })
}

# ---------- DNS (optional) ----------

resource "google_dns_record_set" "monitoring" {
  count = var.dns_zone != "" ? 1 : 0

  managed_zone = var.dns_zone
  name         = var.dns_name
  type         = "A"
  ttl          = 300
  rrdatas      = [google_compute_address.main.address]
}
