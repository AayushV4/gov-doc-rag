resource "aws_ssm_parameter" "guardrail_id" {
  name  = var.store_param_name
  type  = "String"
  value = "UNSET" # overwrite later with your real Guardrail ID
}
