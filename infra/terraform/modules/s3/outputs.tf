output "bucket_arns" {
  value = {
    raw       = aws_s3_bucket.b[var.buckets.raw].arn
    processed = aws_s3_bucket.b[var.buckets.processed].arn
    index     = aws_s3_bucket.b[var.buckets.index].arn
  }
}

output "bucket_names" {
  value = {
    raw       = var.buckets.raw
    processed = var.buckets.processed
    index     = var.buckets.index
  }
}
