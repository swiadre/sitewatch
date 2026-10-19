output "main_ip" {
  value = google_compute_address.main.address
}

output "grafana_url" {
  value = "http://${google_compute_address.main.address}:3000"
}

output "prober_ips" {
  value = { for r, vm in google_compute_instance.prober : r => vm.network_interface[0].network_ip }
}
