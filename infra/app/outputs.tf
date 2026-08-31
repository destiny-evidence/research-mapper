output "web_terminal_url" {
  description = "TEMPORARY proof-of-concept terminal UI, behind Entra sign-in"
  value       = "https://${azurerm_container_app.this.ingress[0].fqdn}"
}

output "identity_client_id" {
  description = "Client ID of the app's managed identity, for granting it DESTINY repository roles"
  value       = azurerm_user_assigned_identity.app.client_id
}

output "identity_principal_id" {
  description = "Object ID of the app's managed identity"
  value       = azurerm_user_assigned_identity.app.principal_id
}

output "database_fqdn" {
  value = azurerm_postgresql_flexible_server.this.fqdn
}

output "web_url" {
  description = "The UI"
  value       = azurerm_storage_account.web.primary_web_endpoint
}

output "api_url" {
  description = "The API the UI calls, behind Keycloak bearer tokens"
  value       = "https://${azurerm_container_app.api.ingress[0].fqdn}"
}
