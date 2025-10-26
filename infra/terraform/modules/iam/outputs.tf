output "api_role_arn" { value = aws_iam_role.api.arn }
output "indexer_role_arn" { value = aws_iam_role.indexer.arn }
output "ingestor_role_arn" { value = aws_iam_role.ingestor.arn }
output "alb_controller_role_arn" { value = aws_iam_role.alb_controller.arn }
output "github_oidc_role_arn" { value = try(aws_iam_role.gha_deploy[0].arn, null) }
output "fluentbit_role_arn" { value = aws_iam_role.fluentbit.arn }
