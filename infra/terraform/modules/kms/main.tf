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

# ---- KMS key for CloudWatch Logs encryption ----
data "aws_iam_policy_document" "logs_kms_policy" {
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
    sid    = "AllowCloudWatchLogs"
    effect = "Allow"
    actions = [
      "kms:Encrypt",
      "kms:Decrypt",
      "kms:ReEncrypt*",
      "kms:GenerateDataKey*",
      "kms:CreateGrant",
      "kms:DescribeKey"
    ]
    resources = ["*"]
    principals {
      type        = "Service"
      identifiers = ["logs.${var.region}.amazonaws.com"]
    }
    condition {
      test     = "ArnLike"
      variable = "kms:EncryptionContext:aws:logs:arn"
      values   = ["arn:aws:logs:${var.region}:${data.aws_caller_identity.current.account_id}:log-group:*"]
    }
  }
}

resource "aws_kms_key" "logs" {
  description         = "KMS key for CloudWatch Logs encryption (gov-doc-rag)"
  enable_key_rotation = true
  policy              = data.aws_iam_policy_document.logs_kms_policy.json
}

resource "aws_kms_alias" "logs_alias" {
  name          = "alias/gov-doc-rag-logs"
  target_key_id = aws_kms_key.logs.key_id
}
