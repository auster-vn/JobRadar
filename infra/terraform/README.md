# Production Infrastructure

This module provisions one protected Hetzner Cloud application host, a deployment
SSH key and an ingress firewall. It intentionally does not manage DNS because the
authoritative DNS provider is deployment-specific.

## Prerequisites

- Terraform 1.10 or newer.
- Access to the HCP Terraform organization `auster-vn-jobradar` and its
  `jobradarvn-production` workspace. The workspace uses local execution: HCP
  Terraform stores and locks state, while provider operations run on the
  operator machine.
- A Hetzner Cloud project token exported as `HCLOUD_TOKEN`.
- A dedicated deployment SSH key and narrow administrative source CIDRs.

Authenticate the Terraform CLI once with `terraform login app.terraform.io`.
Keep the generated credentials file private and never commit credentials,
provider tokens, state or `terraform.tfvars`. HCP Terraform encrypts workspace
state at rest and uses TLS in transit; see the
[HCP Terraform security model](https://developer.hashicorp.com/terraform/cloud-docs/architectural-details/security-model).

## Provision

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan -out=production.tfplan
terraform apply production.tfplan
```

The committed `cloud` block selects exactly one workspace, so do not add a
separate backend configuration. Review every saved plan before apply. A plan
does not create billable resources; apply does.

Create DNS A and AAAA records from the outputs, wait for cloud-init to finish,
then use `deployment_target` to configure the protected GitHub `production`
Environment. Pin `PRODUCTION_KNOWN_HOSTS` from a separately verified host key.
Set the Environment's `HCLOUD_TOKEN` secret and use the `firewall_name` output
for its `HCLOUD_FIREWALL_NAME` variable. Deploy temporarily adds only the
current hosted runner's `/32` or `/128` SSH rule and removes all such managed
rules in an `always()` cleanup; the static administrative CIDRs remain
Terraform-owned.

The default is `cx33`, the current 4-vCPU/8-GB shared Intel plan. The live
Hetzner catalog no longer offers the earlier `cx32` plan for new orders. Verify
the catalog and price again before every production apply; see the
[official Cloud API](https://docs.hetzner.cloud/reference/cloud#tag/server-types)
and the [official Terraform provider](https://registry.terraform.io/providers/hetznercloud/hcloud/latest/docs).
Backups, API deletion/rebuild protection and Terraform `prevent_destroy` are
enabled. Deliberate destruction requires an explicit reviewed code change to
remove `prevent_destroy` before disabling Hetzner protection.
