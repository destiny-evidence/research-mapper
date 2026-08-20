terraform {
  required_version = ">= 1.0"

  cloud {
    organization = "destiny-evidence"

    workspaces {
      project = "DESTINY"
      tags    = ["research-mapper"]
    }
  }

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.1"
    }

    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.8"
    }

    # Container Apps EasyAuth (Microsoft.App/containerApps/authConfigs) has no
    # azurerm resource, so it is provisioned through the raw ARM API.
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.9"
    }

    github = {
      source  = "integrations/github"
      version = "~> 6.13"
    }
  }
}

provider "azurerm" {
  features {}
}

provider "azuread" {
}

provider "azapi" {
}

provider "github" {
  owner = "destiny-evidence"
  app_auth {
    id              = var.github_app_id
    installation_id = var.github_app_installation_id
    pem_file        = var.github_app_pem
  }
}
