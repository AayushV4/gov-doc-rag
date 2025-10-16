variable "project" { type = string }

variable "cluster_version" { type = string }

variable "private_subnet_ids" { type = list(string) }

variable "enable_control_plane_logs" {
  type    = bool
  default = true
}
