# Production Infrastructure

This module provisions one protected Hetzner Cloud application host, a deployment
SSH key and an ingress firewall. It intentionally does not manage DNS because the
authoritative DNS provider is deployment-specific.

## Prerequisites

- Terraform 1.10 or newer.
- A private remote state backend. Copy and configure `backend.tf.example`; never
  commit state or API tokens.
- A Hetzner Cloud project token exported as `HCLOUD_TOKEN`.
- A dedicated deployment SSH key and narrow administrative source CIDRs.

## Provision

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
cp backend.tf.example backend.tf
terraform init
terraform plan -out=production.tfplan
terraform apply production.tfplan
```

Create DNS A and AAAA records from the outputs, wait for cloud-init to finish,
then use `deployment_target` to configure the protected GitHub `production`
Environment. Pin `PRODUCTION_KNOWN_HOSTS` from a separately verified host key.

The default is `cx32`: Hetzner removed the plan's original `cx31` from new API
orders. See the [official deprecation notice](https://docs.hetzner.cloud/changelog#2024-06-06-new-server-plans-with-shared-intel-vcpus)
and the [official Terraform provider](https://registry.terraform.io/providers/hetznercloud/hcloud/latest/docs).
Backups, API deletion/rebuild protection and Terraform `prevent_destroy` are
enabled. Deliberate destruction requires an explicit reviewed code change to
remove `prevent_destroy` before disabling Hetzner protection.
