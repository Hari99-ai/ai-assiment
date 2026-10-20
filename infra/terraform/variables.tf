variable "region" {
  type    = string
  default = "ap-south-1"
}
variable "environment" {
  type    = string
  default = "staging"
}
variable "db_username" {
  type    = string
  default = "amrutam_owner"
}
variable "kubernetes_version" {
  type = string
  # Explicitly choose a version supported by EKS in the deployment region.
}
variable "node_instance_type" {
  type    = string
  default = "t3.medium"
}
variable "redis_auth_token" {
  type        = string
  sensitive   = true
  description = "Redis AUTH token; inject with TF_VAR_redis_auth_token and protect remote state."
  validation {
    condition     = length(var.redis_auth_token) >= 32 && length(var.redis_auth_token) <= 128
    error_message = "Use a randomly generated Redis token of 32 to 128 characters."
  }
}
