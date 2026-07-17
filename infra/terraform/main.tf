resource "hcloud_ssh_key" "deploy" {
  name       = "${var.server_name}-deploy"
  public_key = trimspace(var.ssh_public_key)
  labels = {
    application = "jobradarvn"
    environment = "production"
  }
}

resource "hcloud_firewall" "production" {
  name = "${var.server_name}-firewall"
  labels = {
    application = "jobradarvn"
    environment = "production"
  }

  rule {
    direction   = "in"
    protocol    = "tcp"
    port        = "22"
    source_ips  = var.ssh_allowed_cidrs
    description = "Restricted administrative SSH"
  }

  rule {
    direction   = "in"
    protocol    = "tcp"
    port        = "80"
    source_ips  = ["0.0.0.0/0", "::/0"]
    description = "HTTP for ACME redirect and challenge"
  }

  rule {
    direction   = "in"
    protocol    = "tcp"
    port        = "443"
    source_ips  = ["0.0.0.0/0", "::/0"]
    description = "HTTPS"
  }

  rule {
    direction   = "in"
    protocol    = "udp"
    port        = "443"
    source_ips  = ["0.0.0.0/0", "::/0"]
    description = "HTTP/3"
  }

  rule {
    direction   = "in"
    protocol    = "icmp"
    source_ips  = ["0.0.0.0/0", "::/0"]
    description = "Path MTU discovery and diagnostics"
  }
}

resource "hcloud_server" "production" {
  name         = var.server_name
  server_type  = var.server_type
  image        = var.image
  location     = var.location
  backups      = var.enable_backups
  ssh_keys     = [hcloud_ssh_key.deploy.id]
  firewall_ids = [hcloud_firewall.production.id]
  user_data = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    deployment_user = var.deployment_user
    ssh_public_key  = trimspace(var.ssh_public_key)
  })

  delete_protection        = var.protect_server
  rebuild_protection       = var.protect_server
  shutdown_before_deletion = true

  public_net {
    ipv4_enabled = true
    ipv6_enabled = true
  }

  labels = {
    application = "jobradarvn"
    environment = "production"
    managed_by  = "terraform"
  }

  lifecycle {
    prevent_destroy = true
  }
}
