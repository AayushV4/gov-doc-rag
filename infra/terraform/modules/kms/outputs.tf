output "s3_key_arn" { value = aws_kms_key.s3.arn }
output "secrets_key_arn" { value = aws_kms_key.secrets.arn }
output "logs_key_arn" { value = aws_kms_key.logs.arn }
