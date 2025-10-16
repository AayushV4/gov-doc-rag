data "aws_caller_identity" "current" {}

# ---- KMS key for S3 (allows Textract to read encrypted objects) ----
data "aws_iam_policy_document" "s3_kms_policy" {
  statement {
    sid       = "EnableRootAccount"
    effect    = "Allow"
    actions   = ["kms:*"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }

  statement {
    sid       = "AllowTextractUseOfKey"
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = ["*"]
    principals {
      type        = "Service"
      identifiers = ["textract.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:textract:*:${data.aws_caller_identity.current.account_id}:*"]
    }
  }
}

resource "aws_kms_key" "s3" {
  description         = "KMS key for S3 encryption (gov-doc-rag)"
  enable_key_rotation = true
  policy              = data.aws_iam_policy_document.s3_kms_policy.json
}

resource "aws_kms_alias" "s3_alias" {
  name          = "alias/gov-doc-rag-s3"
  target_key_id = aws_kms_key.s3.key_id
}

# ---- KMS key for Secrets Manager (root account controls; Secrets Manager grants are handled by service) ----
resource "aws_kms_key" "secrets" {
  description         = "KMS key for Secrets Manager (gov-doc-rag)"
  enable_key_rotation = true
}

resource "aws_kms_alias" "secrets_alias" {
  name          = "alias/gov-doc-rag-secrets"
  target_key_id = aws_kms_key.secrets.key_id
}
