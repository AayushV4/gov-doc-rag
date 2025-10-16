output "interface_endpoints" { value = [for k, v in aws_vpc_endpoint.iface : v.id] }
output "s3_endpoint_id" { value = aws_vpc_endpoint.s3.id }
