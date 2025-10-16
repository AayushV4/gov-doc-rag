output "kubeconfig_hint" {
  value = "Run: aws eks update-kubeconfig --region ${var.region} --name ${module.eks.cluster_name}"
}

output "raw_bucket" { value = module.s3.bucket_names["raw"] }
output "processed_bucket" { value = module.s3.bucket_names["processed"] }
output "index_bucket" { value = module.s3.bucket_names["index"] }

output "s3_kms_key_arn" { value = module.kms.s3_key_arn }
output "secrets_kms_key_arn" { value = module.kms.secrets_key_arn }

output "service_iam_roles" {
  value = {
    api_role_arn            = module.iam.api_role_arn
    indexer_role_arn        = module.iam.indexer_role_arn
    ingestor_role_arn       = module.iam.ingestor_role_arn
    alb_controller_role_arn = module.iam.alb_controller_role_arn
    github_oidc_role_arn    = try(module.iam.github_oidc_role_arn, null)
  }
}
