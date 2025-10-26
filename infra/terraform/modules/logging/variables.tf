variable "project" {
  description = "Project name"
  type        = string
}

variable "cluster_name" {
  description = "EKS cluster name"
  type        = string
}

variable "log_retention_days" {
  description = "Number of days to retain logs in CloudWatch"
  type        = number
  default     = 30

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 3653], var.log_retention_days)
    error_message = "Log retention must be a valid CloudWatch retention period."
  }
}

variable "logs_kms_key_arn" {
  description = "ARN of KMS key for encrypting CloudWatch logs"
  type        = string
}

variable "enable_log_insights" {
  description = "Create CloudWatch Log Insights saved queries"
  type        = bool
  default     = true
}
