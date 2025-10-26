variable "project" {
  description = "Project name prefix"
  type        = string
  default     = "gov-doc-rag"
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "eks_version" {
  description = "EKS Kubernetes version"
  type        = string
  default     = "1.29"
}

variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}

variable "azs" {
  type    = list(string)
  default = ["us-east-1a", "us-east-1b"]
}

variable "public_subnets" {
  type    = list(string)
  default = ["10.20.0.0/24", "10.20.1.0/24"]
}

variable "private_subnets" {
  type    = list(string)
  default = ["10.20.10.0/24", "10.20.11.0/24"]
}

variable "raw_bucket" {
  type    = string
  default = "gov-doc-raw"
}

variable "processed_bucket" {
  type    = string
  default = "gov-doc-processed"
}

variable "index_bucket" {
  type    = string
  default = "gov-doc-index"
}

variable "budget_limit" {
  description = "Monthly budget limit in USD"
  type        = number
  default     = 50
}

variable "budget_emails" {
  description = "Emails to notify for budget alerts"
  type        = list(string)
  default     = []
}

variable "create_guardrail" {
  description = "If true, attempt to create a Bedrock guardrail (requires AWS provider support). Otherwise only stores ID parameter."
  type        = bool
  default     = false
}

variable "guardrail_content" {
  description = "Optional JSON content/rules for a guardrail if create_guardrail = true"
  type        = string
  default     = ""
}

variable "create_github_oidc" {
  description = "Create GitHub Actions OIDC role for CI/CD (used in Phase 6)"
  type        = bool
  default     = false
}

variable "github_org" {
  type    = string
  default = ""
}

variable "github_repo" {
  type    = string
  default = ""
}

variable "log_retention_days" {
  description = "Number of days to retain CloudWatch logs"
  type        = number
  default     = 30

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 3653], var.log_retention_days)
    error_message = "Log retention must be a valid CloudWatch retention period."
  }
}
