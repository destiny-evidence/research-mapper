variable "app_name" {
  type        = string
  default     = "research-mapper"
  description = "Application name"
}

variable "environment" {
  description = "The environment this stack is being deployed to (development, staging, production)"
  type        = string
  validation {
    condition     = contains(["development", "staging", "production"], var.environment)
    error_message = "Allowed values for input_parameter are \"development\", \"staging\", or \"production\"."
  }
}

variable "region" {
  description = "The Azure region resources will be deployed into"
  type        = string
  default     = "swedencentral"
}

variable "budget_code" {
  description = "Budget code for tagging resource groups. Required tag for resource groups"
  type        = string
}

variable "created_by" {
  description = "Creator of this infrastructure"
  type        = string
}

variable "owner" {
  description = "Owner email for this infrastructure"
  type        = string
}

variable "project" {
  description = "Project name for tagging"
  type        = string
  default     = "DESTINY"
}

# GitHub Actions
variable "github_repo" {
  type        = string
  default     = "destiny-evidence/research-mapper"
  description = "GitHub repository for Actions OIDC"
}

variable "github_app_id" {
  description = "GitHub App ID for configuring repository environments"
  type        = string
}

variable "github_app_installation_id" {
  description = "GitHub App installation ID"
  type        = string
}

variable "github_app_pem" {
  description = "GitHub App private key PEM file contents"
  type        = string
  sensitive   = true
}

# Container Registry (shared)
variable "shared_container_registry_name" {
  description = "The name of the shared container registry"
  type        = string
}

variable "shared_resource_group_name" {
  description = "The resource group containing the shared container registry"
  type        = string
}

# DESTINY repository
variable "destiny_repository_application_id" {
  description = "Client ID of the DESTINY repository's Entra application, used as the token audience"
  type        = string
}

# LLM
variable "llm_base_url" {
  description = "Base URL of the LLM endpoint"
  type        = string
}

variable "llm_model" {
  description = "LiteLLM model identifier"
  type        = string
  default     = "azure/gpt-4.1"
}

variable "llm_api_key" {
  description = "API key for the LLM endpoint"
  type        = string
  sensitive   = true
}

# Keycloak

variable "keycloak_url" {
  description = "Base URL of the Keycloak instance"
  type        = string
  default     = "https://auth.evidence-repository.org"
}

variable "keycloak_realm" {
  description = "Keycloak realm holding the research-mapper client"
  type        = string
  default     = "destiny"
}
