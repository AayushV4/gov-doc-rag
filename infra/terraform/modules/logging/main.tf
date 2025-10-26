# CloudWatch Log Groups for gov-doc-rag application logging

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/eks/${var.cluster_name}/application/api"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.logs_kms_key_arn

  tags = {
    Project     = var.project
    Environment = "production"
    Service     = "api"
    ManagedBy   = "terraform"
  }
}

resource "aws_cloudwatch_log_group" "ingestor" {
  name              = "/aws/eks/${var.cluster_name}/application/ingestor"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.logs_kms_key_arn

  tags = {
    Project     = var.project
    Environment = "production"
    Service     = "ingestor"
    ManagedBy   = "terraform"
  }
}

resource "aws_cloudwatch_log_group" "indexer" {
  name              = "/aws/eks/${var.cluster_name}/application/indexer"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.logs_kms_key_arn

  tags = {
    Project     = var.project
    Environment = "production"
    Service     = "indexer"
    ManagedBy   = "terraform"
  }
}

resource "aws_cloudwatch_log_group" "web" {
  name              = "/aws/eks/${var.cluster_name}/application/web"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.logs_kms_key_arn

  tags = {
    Project     = var.project
    Environment = "production"
    Service     = "web"
    ManagedBy   = "terraform"
  }
}

# Container logs from FluentBit
resource "aws_cloudwatch_log_group" "containers" {
  name              = "/aws/eks/${var.cluster_name}/containers"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.logs_kms_key_arn

  tags = {
    Project     = var.project
    Environment = "production"
    ManagedBy   = "terraform"
  }
}

# Data plane logs (kubelet, kube-proxy, etc.)
resource "aws_cloudwatch_log_group" "dataplane" {
  name              = "/aws/eks/${var.cluster_name}/dataplane"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.logs_kms_key_arn

  tags = {
    Project     = var.project
    Environment = "production"
    ManagedBy   = "terraform"
  }
}

# CloudWatch Log Insights queries for common debugging scenarios
resource "aws_cloudwatch_query_definition" "error_rate" {
  count = var.enable_log_insights ? 1 : 0

  name = "${var.project}-error-rate"

  log_group_names = [
    aws_cloudwatch_log_group.api.name,
    aws_cloudwatch_log_group.ingestor.name,
    aws_cloudwatch_log_group.indexer.name,
  ]

  query_string = <<-QUERY
    fields @timestamp, logger, message, error
    | filter level = "ERROR"
    | stats count() as error_count by bin(5m)
    | sort @timestamp desc
  QUERY
}

resource "aws_cloudwatch_query_definition" "slow_requests" {
  count = var.enable_log_insights ? 1 : 0

  name = "${var.project}-slow-requests"

  log_group_names = [
    aws_cloudwatch_log_group.api.name,
  ]

  query_string = <<-QUERY
    fields @timestamp, message, duration_seconds, query_length
    | filter duration_seconds > 5
    | sort duration_seconds desc
    | limit 100
  QUERY
}

resource "aws_cloudwatch_query_definition" "document_processing" {
  count = var.enable_log_insights ? 1 : 0

  name = "${var.project}-document-processing"

  log_group_names = [
    aws_cloudwatch_log_group.ingestor.name,
    aws_cloudwatch_log_group.indexer.name,
  ]

  query_string = <<-QUERY
    fields @timestamp, message, doc_id, num_pages, num_chunks, duration_seconds
    | filter message like /completed/i
    | sort @timestamp desc
  QUERY
}
