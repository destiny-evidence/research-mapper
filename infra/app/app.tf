data "azurerm_subscription" "current" {}

data "azuread_client_config" "current" {}

resource "azurerm_resource_group" "this" {
  name     = "rg-${local.name}"
  location = var.region
  tags     = merge({ "Budget Code" = var.budget_code }, local.minimum_resource_tags)
}

data "azurerm_container_registry" "this" {
  name                = var.shared_container_registry_name
  resource_group_name = var.shared_resource_group_name
}

resource "azurerm_user_assigned_identity" "app" {
  name                = local.name
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.minimum_resource_tags
}

resource "azurerm_role_assignment" "app_acr_pull" {
  principal_id         = azurerm_user_assigned_identity.app.principal_id
  scope                = data.azurerm_container_registry.this.id
  role_definition_name = "AcrPull"
}

resource "azurerm_log_analytics_workspace" "this" {
  name                = local.name
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.minimum_resource_tags
}

resource "azurerm_container_app_environment" "this" {
  name                       = local.name
  location                   = azurerm_resource_group.this.location
  resource_group_name        = azurerm_resource_group.this.name
  logs_destination           = "log-analytics"
  log_analytics_workspace_id = azurerm_log_analytics_workspace.this.id
  infrastructure_subnet_id   = azurerm_subnet.app.id
  tags                       = local.minimum_resource_tags

  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
  }
}

resource "azurerm_container_app" "this" {
  name                         = local.name
  resource_group_name          = azurerm_resource_group.this.name
  container_app_environment_id = azurerm_container_app_environment.this.id
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"
  tags                         = local.minimum_resource_tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = data.azurerm_container_registry.this.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  secret {
    name  = "llm-api-key"
    value = var.llm_api_key
  }

  secret {
    name  = "easyauth-client-secret"
    value = azuread_application_password.easyauth.value
  }

  ingress {
    external_enabled           = true
    allow_insecure_connections = false
    target_port                = 8080
    transport                  = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 1
    max_replicas = 1

    container {
      name = "research-mapper"

      # Placeholder only. The deploy workflow owns the image from then on, and
      # the lifecycle block below stops Terraform reverting it.
      image  = "mcr.microsoft.com/k8se/quickstart:latest"
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.app.client_id
      }

      env {
        name  = "MAPPER_DESTINY_APPLICATION_ID"
        value = var.destiny_repository_application_id
      }

      env {
        name  = "MAPPER_DESTINY_ENV"
        value = var.environment
      }

      env {
        name  = "MAPPER_LLM_BASE_URL"
        value = var.llm_base_url
      }

      env {
        name  = "MAPPER_LLM_MODEL"
        value = var.llm_model
      }

      env {
        name        = "MAPPER_LLM_API_KEY"
        secret_name = "llm-api-key"
      }

      env {
        name  = "MAPPER_DB_HOST"
        value = azurerm_postgresql_flexible_server.this.fqdn
      }

      env {
        name  = "MAPPER_DB_NAME"
        value = azurerm_postgresql_flexible_server_database.this.name
      }

      env {
        name  = "MAPPER_DB_USER"
        value = azurerm_user_assigned_identity.app.name
      }
    }
  }

  # The deploy workflow, not Terraform, owns which image tag is live.
  lifecycle {
    ignore_changes = [template[0].container[0].image]
  }
}
