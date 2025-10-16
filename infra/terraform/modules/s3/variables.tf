variable "project" { type = string }
variable "s3_kms_key_arn" { type = string }
variable "buckets" {
  type = object({
    raw       = string
    processed = string
    index     = string
  })
}
