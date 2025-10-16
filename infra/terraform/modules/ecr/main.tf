resource "aws_ecr_repository" "repo" {
  for_each = toset(var.repos)
  name     = "${var.project}-${each.value}"
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = var.kms_key_arn
  }
  tags = { Name = "${var.project}-${each.value}" }
}
