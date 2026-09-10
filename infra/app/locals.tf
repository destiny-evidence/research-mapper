locals {
  env_short = { production = "prod", development = "dev" }
  env       = lookup(local.env_short, var.environment, var.environment)

  name       = "${var.app_name}-${local.env}"
  name_short = "${replace(var.app_name, "-", "")}${substr(var.environment, 0, 4)}"
  minimum_resource_tags = {
    "Created by"  = var.created_by
    "Environment" = var.environment
    "Owner"       = var.owner
    "Project"     = var.project
    "Region"      = var.region
  }
}

locals {
  keycloak_client_id = "research-mapper-ui-${var.environment}"
  keycloak_issuer    = "${var.keycloak_url}/realms/${var.keycloak_realm}"

  web_origin = trimsuffix(azurerm_storage_account.web.primary_web_endpoint, "/")
}
