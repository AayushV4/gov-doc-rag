resource "aws_secretsmanager_secret" "s" {
  for_each   = toset(var.secret_names)
  name       = "${var.project}/${each.value}"
  kms_key_id = var.secrets_kms_key_arn
  tags       = { project = var.project }
}

# Create an initial non-empty value so Terraform can succeed; you will overwrite later.
resource "aws_secretsmanager_secret_version" "sv" {
  for_each      = aws_secretsmanager_secret.s
  secret_id     = each.value.id
  secret_string = "PLACEHOLDER"
}
