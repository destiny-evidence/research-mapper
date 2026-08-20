# ---------------------------------------------------------------------------
# TEMPORARY. The container app serves research-mapper's terminal UI over the
# web via ttyd. Once we have an authenticated API in this app this should be
# removed in favour of a Keycloak integration.
# ---------------------------------------------------------------------------

resource "azuread_application_registration" "easyauth" {
  display_name                       = "${local.name}-web-terminal"
  sign_in_audience                   = "AzureADMyOrg"
  implicit_id_token_issuance_enabled = true
}

resource "azuread_service_principal" "easyauth" {
  client_id = azuread_application_registration.easyauth.client_id
  owners    = [data.azuread_client_config.current.object_id]
}

resource "azuread_application_password" "easyauth" {
  application_id = azuread_application_registration.easyauth.id
}

# The callback URL is only knowable once the container app has an FQDN, hence
# the separate resource.
resource "azuread_application_redirect_uris" "easyauth" {
  application_id = azuread_application_registration.easyauth.id
  type           = "Web"
  redirect_uris  = ["https://${azurerm_container_app.this.ingress[0].fqdn}/.auth/login/aad/callback"]
}

# Container Apps EasyAuth has no azurerm resource, so it goes through the ARM
# API directly.
resource "azapi_resource" "easyauth" {
  type      = "Microsoft.App/containerApps/authConfigs@2024-03-01"
  name      = "current"
  parent_id = azurerm_container_app.this.id

  body = {
    properties = {
      platform = {
        enabled = true
      }
      globalValidation = {
        unauthenticatedClientAction = "RedirectToLoginPage"
        redirectToProvider          = "azureactivedirectory"
      }
      identityProviders = {
        azureActiveDirectory = {
          enabled = true
          registration = {
            openIdIssuer            = "https://login.microsoftonline.com/${data.azurerm_subscription.current.tenant_id}/v2.0"
            clientId                = azuread_application_registration.easyauth.client_id
            clientSecretSettingName = "easyauth-client-secret"
          }
          validation = {
            allowedAudiences = [azuread_application_registration.easyauth.client_id]
          }
        }
      }
    }
  }
}
