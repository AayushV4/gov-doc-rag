terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.48.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.29.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = ">= 2.12.1"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.6.0"
    }
  }
}

provider "aws" {
  region = var.region
}

# ---------- VPC ----------
module "vpc" {
  source = "./modules/vpc"

  name            = "${var.project}-vpc"
  cidr_block      = var.vpc_cidr
  azs             = var.azs
  public_subnets  = var.public_subnets
  private_subnets = var.private_subnets
}

# ---------- KMS ----------
module "kms" {
  source = "./modules/kms"

  project = var.project
  region  = var.region
}

# ---------- CloudWatch Logging ----------
module "logging" {
  source = "./modules/logging"

  project             = var.project
  cluster_name        = module.eks.cluster_name
  log_retention_days  = var.log_retention_days
  logs_kms_key_arn    = module.kms.logs_key_arn
  enable_log_insights = true

  depends_on = [module.eks]
}

# ---------- S3 ----------
module "s3" {
  source = "./modules/s3"

  project        = var.project
  s3_kms_key_arn = module.kms.s3_key_arn
  buckets = {
    raw       = var.raw_bucket
    processed = var.processed_bucket
    index     = var.index_bucket
  }
}

# ---------- ECR ----------
module "ecr" {
  source      = "./modules/ecr"
  project     = var.project
  repos       = ["api", "indexer", "ingestor", "web"]
  kms_key_arn = module.kms.s3_key_arn
}

# ---------- EKS ----------
module "eks" {
  source = "./modules/eks"

  project                   = var.project
  cluster_version           = var.eks_version
  private_subnet_ids        = module.vpc.private_subnet_ids
  enable_control_plane_logs = true
}

# ---------- VPC Endpoints ----------
module "vpc_endpoints" {
  source = "./modules/vpc_endpoints"

  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  endpoint_sg_cidr   = var.vpc_cidr
  route_table_ids    = [module.vpc.private_route_table_id, module.vpc.public_route_table_id]
}

# ---------- IAM (IRSA roles for services + ALB controller) ----------
module "iam" {
  source       = "./modules/iam"
  region       = var.region
  cluster_name = module.eks.cluster_name

  project                   = var.project
  cluster_oidc_provider_arn = module.eks.oidc_provider_arn
  cluster_oidc_provider_url = module.eks.oidc_provider_url

  raw_bucket_arn       = module.s3.bucket_arns["raw"]
  processed_bucket_arn = module.s3.bucket_arns["processed"]
  index_bucket_arn     = module.s3.bucket_arns["index"]

  s3_kms_key_arn      = module.kms.s3_key_arn
  secrets_kms_key_arn = module.kms.secrets_key_arn
  secrets_prefix      = "/${var.project}/"

  create_github_oidc = var.create_github_oidc
  github_org         = var.github_org
  github_repo        = var.github_repo
}

# ---------- Secrets Manager placeholders ----------
module "secrets" {
  source = "./modules/secrets"

  project             = var.project
  secrets_kms_key_arn = module.kms.secrets_key_arn
  secret_names = [
    "PINECONE_API_KEY",
    "PINECONE_ENVIRONMENT",
    "PINECONE_INDEX",
    "BEDROCK_GUARDRAIL_ID"
  ]
}

# ---------- Budgets ----------
module "budgets" {
  source           = "./modules/budgets"
  project          = var.project
  budget_limit     = var.budget_limit
  email_recipients = var.budget_emails
}

# ---------- Bedrock Guardrails (optional create, default: just store ID) ----------
module "guardrails" {
  source = "./modules/guardrails"

  project               = var.project
  create_guardrail      = var.create_guardrail
  guardrail_name        = "${var.project}-guardrail"
  guardrail_description = "Baseline guardrail for ${var.project}"
  guardrail_content     = var.guardrail_content
  store_param_name      = "/${var.project}/BEDROCK_GUARDRAIL_ID"
}

# Kubernetes provider uses EKS outputs + aws eks get-token
provider "kubernetes" {
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_ca)

  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name]
  }
}

# Helm provider wired to the same Kubernetes connection (attribute style)
provider "helm" {
  kubernetes = {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_ca)
    exec = {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name]
    }
  }
}



# ---------- AWS Load Balancer Controller via Helm ----------
module "alb_ingress" {
  source = "./modules/alb_ingress"

  project              = var.project
  cluster_name         = module.eks.cluster_name
  region               = var.region
  vpc_id               = module.vpc.vpc_id
  service_account_name = "aws-load-balancer-controller"
  namespace            = "kube-system"
  controller_role_arn  = module.iam.alb_controller_role_arn

  providers = {
    helm       = helm
    kubernetes = kubernetes
  }

  depends_on = [module.eks]
}

output "cluster_name" { value = module.eks.cluster_name }
output "cluster_endpoint" { value = module.eks.cluster_endpoint }
output "ecr_repos" { value = module.ecr.repo_urls }
output "buckets" { value = module.s3.bucket_names }
output "oidc_provider_arn" { value = module.eks.oidc_provider_arn }
output "alb_controller_sa" { value = module.alb_ingress.service_account_name }
output "log_groups" {
  value = {
    api        = module.logging.api_log_group_name
    ingestor   = module.logging.ingestor_log_group_name
    indexer    = module.logging.indexer_log_group_name
    containers = module.logging.containers_log_group_name
    dataplane  = module.logging.dataplane_log_group_name
  }
}
