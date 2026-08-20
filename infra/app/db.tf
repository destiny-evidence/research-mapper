# Cheapest burstable tier, no HA, no geo-redundancy. Reachable only from the
# vnet, and only by Entra identities -- password auth is off entirely.

resource "azurerm_postgresql_flexible_server" "this" {
  name                          = local.name
  resource_group_name           = azurerm_resource_group.this.name
  location                      = azurerm_resource_group.this.location
  version                       = "16"
  sku_name                      = "B_Standard_B1ms"
  storage_mb                    = 32768
  backup_retention_days         = 7
  delegated_subnet_id           = azurerm_subnet.db.id
  private_dns_zone_id           = azurerm_private_dns_zone.db.id
  public_network_access_enabled = false
  tags                          = local.minimum_resource_tags

  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = false
  }

  depends_on = [azurerm_private_dns_zone_virtual_network_link.db]
}

# Making the app's identity the server administrator means it can connect with
# no in-database user provisioning -- which would otherwise need a bootstrap
# job inside the vnet, since the server isn't reachable from Terraform.
resource "azurerm_postgresql_flexible_server_active_directory_administrator" "app" {
  server_name         = azurerm_postgresql_flexible_server.this.name
  resource_group_name = azurerm_resource_group.this.name
  tenant_id           = data.azurerm_subscription.current.tenant_id
  object_id           = azurerm_user_assigned_identity.app.principal_id
  principal_name      = azurerm_user_assigned_identity.app.name
  principal_type      = "ServicePrincipal"
}

resource "azurerm_postgresql_flexible_server_database" "this" {
  name      = "research_mapper"
  server_id = azurerm_postgresql_flexible_server.this.id
  collation = "en_US.utf8"
  charset   = "UTF8"
}
