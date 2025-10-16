variable "project" { type = string }

variable "cluster_oidc_provider_arn" { type = string }
variable "cluster_oidc_provider_url" { type = string }

variable "raw_bucket_arn" { type = string }
variable "processed_bucket_arn" { type = string }
variable "index_bucket_arn" { type = string }

variable "s3_kms_key_arn" { type = string }
variable "secrets_kms_key_arn" { type = string }
variable "secrets_prefix" { type = string }

variable "create_github_oidc" { type = bool }
variable "github_org" { type = string }
variable "github_repo" { type = string }
