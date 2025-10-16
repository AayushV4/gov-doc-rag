locals {
  bucket_map = {
    (var.buckets.raw)       = "raw"
    (var.buckets.processed) = "processed"
    (var.buckets.index)     = "index"
  }
}

resource "aws_s3_bucket" "b" {
  for_each = local.bucket_map
  bucket   = each.key
  tags     = { Name = "${var.project}-${each.value}" }
}

resource "aws_s3_bucket_versioning" "v" {
  for_each = aws_s3_bucket.b
  bucket   = each.value.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "enc" {
  for_each = aws_s3_bucket.b
  bucket   = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = var.s3_kms_key_arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "block" {
  for_each                = aws_s3_bucket.b
  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  restrict_public_buckets = true
  ignore_public_acls      = true
}

# --- Allow Textract to read from gov-doc-raw bucket (same-account, tightly scoped) ---
data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "raw_allow_textract" {
  statement {
    sid       = "AllowTextractListRawBucket"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.b["gov-doc-raw"].arn]
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

  statement {
    sid       = "AllowTextractGetRawObjects"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.b["gov-doc-raw"].arn}/*"]
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

resource "aws_s3_bucket_policy" "raw_allow_textract" {
  bucket = aws_s3_bucket.b["gov-doc-raw"].id
  policy = data.aws_iam_policy_document.raw_allow_textract.json
}
