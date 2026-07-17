variable "server_name" {
  description = "Hetzner server and resource name prefix."
  type        = string
  default     = "jobradarvn-production"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.server_name))
    error_message = "server_name must be a lowercase DNS-compatible name."
  }
}

variable "server_type" {
  description = "Current shared Intel server type; CX31 is no longer orderable."
  type        = string
  default     = "cx32"
}

variable "location" {
  description = "Hetzner location, for example nbg1, fsn1 or hel1."
  type        = string
  default     = "nbg1"
}

variable "image" {
  description = "Base operating-system image."
  type        = string
  default     = "ubuntu-24.04"
}

variable "deployment_user" {
  description = "Non-root account used by GitHub Actions."
  type        = string
  default     = "jobradar"

  validation {
    condition     = can(regex("^[a-z_][a-z0-9_-]{0,30}$", var.deployment_user))
    error_message = "deployment_user must be a valid Linux account name."
  }
}

variable "ssh_public_key" {
  description = "OpenSSH public key installed for the deployment user."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^ssh-(ed25519|rsa) ", trimspace(var.ssh_public_key)))
    error_message = "ssh_public_key must be an ed25519 or RSA OpenSSH public key."
  }
}

variable "ssh_allowed_cidrs" {
  description = "IPv4/IPv6 CIDRs allowed to reach SSH. Never use a public default."
  type        = list(string)

  validation {
    condition = (
      length(var.ssh_allowed_cidrs) > 0
      && alltrue([for cidr in var.ssh_allowed_cidrs : can(cidrhost(cidr, 0))])
    )
    error_message = "ssh_allowed_cidrs must contain at least one valid CIDR."
  }
}

variable "enable_backups" {
  description = "Enable Hetzner-managed server backups."
  type        = bool
  default     = true
}

variable "protect_server" {
  description = "Enable Hetzner API deletion and rebuild protection. Terraform prevent_destroy remains enforced."
  type        = bool
  default     = true
}
