mock_provider "hcloud" {}

run "secure_production_defaults" {
  command = plan

  variables {
    ssh_public_key    = "ssh-ed25519 AAAATEST deployment@example"
    ssh_allowed_cidrs = ["203.0.113.10/32"]
  }

  assert {
    condition     = hcloud_server.production.server_type == "cx32"
    error_message = "The production default must use the current CX32 plan."
  }

  assert {
    condition     = hcloud_server.production.image == "ubuntu-24.04"
    error_message = "The production image must remain on Ubuntu 24.04."
  }

  assert {
    condition     = can(yamldecode(hcloud_server.production.user_data))
    error_message = "Rendered cloud-init must remain valid YAML."
  }

  assert {
    condition = alltrue([
      strcontains(hcloud_server.production.user_data, "\"log-driver\": \"local\""),
      strcontains(hcloud_server.production.user_data, "\"max-size\": \"10m\""),
      strcontains(hcloud_server.production.user_data, "\"max-file\": \"3\""),
    ])
    error_message = "Cloud-init must configure bounded Docker log rotation."
  }

  assert {
    condition = (
      hcloud_server.production.backups
      && hcloud_server.production.delete_protection
      && hcloud_server.production.rebuild_protection
    )
    error_message = "Backups and provider-level protections must default to enabled."
  }

  assert {
    condition = length([
      for rule in hcloud_firewall.production.rule : rule
      if rule.protocol == "tcp"
      && rule.port == "22"
      && rule.source_ips == toset(["203.0.113.10/32"])
    ]) == 1
    error_message = "SSH ingress must use only the explicitly supplied CIDRs."
  }
}

run "rejects_empty_ssh_allowlist" {
  command = plan

  variables {
    ssh_public_key    = "ssh-ed25519 AAAATEST deployment@example"
    ssh_allowed_cidrs = []
  }

  expect_failures = [var.ssh_allowed_cidrs]
}
