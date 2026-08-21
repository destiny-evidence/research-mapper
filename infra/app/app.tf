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

# Every container runs the same image, so they need the same configuration. The
# LLM key is a secret and stays a literal env block in each template.
locals {
  app_env = {
    AZURE_CLIENT_ID               = azurerm_user_assigned_identity.app.client_id
    MAPPER_DESTINY_APPLICATION_ID = var.destiny_repository_application_id
    MAPPER_DESTINY_ENV            = var.environment
    MAPPER_LLM_BASE_URL           = var.llm_base_url
    MAPPER_LLM_MODEL              = var.llm_model
    MAPPER_DB_HOST                = azurerm_postgresql_flexible_server.this.fqdn
    MAPPER_DB_NAME                = azurerm_postgresql_flexible_server_database.this.name
    MAPPER_DB_USER                = azurerm_user_assigned_identity.app.name
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

      dynamic "env" {
        for_each = local.app_env
        content {
          name  = env.key
          value = env.value
        }
      }

      env {
        name        = "MAPPER_LLM_API_KEY"
        secret_name = "llm-api-key"
      }
    }
  }

  # The deploy workflow, not Terraform, owns which image tag is live.
  lifecycle {
    ignore_changes = [template[0].container[0].image]
  }
}

resource "azurerm_container_app_job" "migrate" {
  name                         = "db-migrator-${var.environment}"
  resource_group_name          = azurerm_resource_group.this.name
  location                     = azurerm_resource_group.this.location
  container_app_environment_id = azurerm_container_app_environment.this.id
  workload_profile_name        = "Consumption"
  replica_timeout_in_seconds   = 600
  replica_retry_limit          = 1
  tags                         = local.minimum_resource_tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = data.azurerm_container_registry.this.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }

  template {
    container {
      name    = "migrate"
      image   = "mcr.microsoft.com/k8se/quickstart:latest"
      cpu     = 0.5
      memory  = "1Gi"
      command = ["python", "-m", "research_mapper", "migrate"]

      dynamic "env" {
        for_each = local.app_env
        content {
          name  = env.key
          value = env.value
        }
      }
    }
  }

  # The deploy workflow, not Terraform, owns which image tag is live.
  lifecycle {
    ignore_changes = [template[0].container[0].image]
  }
}

# The worker shares nothing with the API but the database. It gets its own
# container so a fan-out of LLM calls can't starve request serving.
resource "azurerm_container_app" "worker" {
  name                         = "${local.name}-worker"
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

  template {
    min_replicas = 1
    max_replicas = 1

    container {
      name = "worker"

      # Placeholder only. The deploy workflow owns the image from then on, and
      # the lifecycle block below stops Terraform reverting it.
      image   = "mcr.microsoft.com/k8se/quickstart:latest"
      cpu     = 1.0
      memory  = "2Gi"
      command = ["python", "-m", "research_mapper", "worker"]

      dynamic "env" {
        for_each = local.app_env
        content {
          name  = env.key
          value = env.value
        }
      }

      env {
        name        = "MAPPER_LLM_API_KEY"
        secret_name = "llm-api-key"
      }
    }
  }

  # The deploy workflow, not Terraform, owns which image tag is live.
  lifecycle {
    ignore_changes = [template[0].container[0].image]
  }
}
