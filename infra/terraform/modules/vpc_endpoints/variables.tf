variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "endpoint_sg_cidr" { type = string }
variable "route_table_ids" { type = list(string) }
