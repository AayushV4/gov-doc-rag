output "api_log_group_name" {
  description = "Name of the API application log group"
  value       = aws_cloudwatch_log_group.api.name
}

output "api_log_group_arn" {
  description = "ARN of the API application log group"
  value       = aws_cloudwatch_log_group.api.arn
}

output "ingestor_log_group_name" {
  description = "Name of the ingestor application log group"
  value       = aws_cloudwatch_log_group.ingestor.name
}

output "ingestor_log_group_arn" {
  description = "ARN of the ingestor application log group"
  value       = aws_cloudwatch_log_group.ingestor.arn
}

output "indexer_log_group_name" {
  description = "Name of the indexer application log group"
  value       = aws_cloudwatch_log_group.indexer.name
}

output "indexer_log_group_arn" {
  description = "ARN of the indexer application log group"
  value       = aws_cloudwatch_log_group.indexer.arn
}

output "containers_log_group_name" {
  description = "Name of the containers log group"
  value       = aws_cloudwatch_log_group.containers.name
}

output "dataplane_log_group_name" {
  description = "Name of the dataplane log group"
  value       = aws_cloudwatch_log_group.dataplane.name
}

output "all_log_group_arns" {
  description = "List of all log group ARNs for IAM policy attachment"
  value = [
    aws_cloudwatch_log_group.api.arn,
    aws_cloudwatch_log_group.ingestor.arn,
    aws_cloudwatch_log_group.indexer.arn,
    aws_cloudwatch_log_group.web.arn,
    aws_cloudwatch_log_group.containers.arn,
    aws_cloudwatch_log_group.dataplane.arn,
  ]
}
