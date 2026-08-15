terraform {
  required_version = ">= 1.10.0, < 2.0.0"

  cloud {
    organization = "auster-vn-jobradar"

    workspaces {
      name = "jobradarvn-production"
    }
  }

  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.66"
    }
  }
}

provider "hcloud" {}
