output "server_id" {
  description = "Hetzner Cloud server ID."
  value       = hcloud_server.production.id
}

output "ipv4_address" {
  description = "Create the production DNS A record with this address."
  value       = hcloud_server.production.ipv4_address
}

output "ipv6_address" {
  description = "Create the production DNS AAAA record with this address."
  value       = hcloud_server.production.ipv6_address
}

output "firewall_name" {
  description = "Value for GitHub's HCLOUD_FIREWALL_NAME production variable."
  value       = hcloud_firewall.production.name
}

output "deployment_target" {
  description = "Value for GitHub's PRODUCTION_USER and PRODUCTION_HOST secrets."
  value = {
    user = var.deployment_user
    host = hcloud_server.production.ipv4_address
  }
}
