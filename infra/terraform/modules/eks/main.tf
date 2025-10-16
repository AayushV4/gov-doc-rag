terraform {
  required_providers {
    tls = {
      source  = "hashicorp/tls"
      version = ">= 4.0.5"
    }
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.48.0"
    }
  }
}

# --- EKS control plane role ---
resource "aws_iam_role" "eks" {
  name               = "${var.project}-eks-role"
  assume_role_policy = data.aws_iam_policy_document.eks_assume.json
}

data "aws_iam_policy_document" "eks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy_attachment" "eks_policy" {
  role       = aws_iam_role.eks.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

# --- EKS cluster ---
resource "aws_eks_cluster" "this" {
  name     = "${var.project}-cluster"
  role_arn = aws_iam_role.eks.arn
  version  = var.cluster_version

  vpc_config {
    subnet_ids = var.private_subnet_ids
  }

  enabled_cluster_log_types = var.enable_control_plane_logs ? ["api", "audit", "authenticator", "controllerManager", "scheduler"] : []

  depends_on = [aws_iam_role_policy_attachment.eks_policy]
}

# --- Node group role ---
resource "aws_iam_role" "node" {
  name               = "${var.project}-node-role"
  assume_role_policy = data.aws_iam_policy_document.node_assume.json
}

data "aws_iam_policy_document" "node_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy_attachment" "worker_node" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}

resource "aws_iam_role_policy_attachment" "cni" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}

resource "aws_iam_role_policy_attachment" "ecr_pull" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_eks_node_group" "default" {
  cluster_name    = aws_eks_cluster.this.name
  node_group_name = "default"
  node_role_arn   = aws_iam_role.node.arn
  subnet_ids      = var.private_subnet_ids

  scaling_config {
    desired_size = 2
    max_size     = 3
    min_size     = 1
  }

  ami_type       = "AL2_x86_64"
  instance_types = ["t3.large"]

  depends_on = [
    aws_iam_role_policy_attachment.worker_node,
    aws_iam_role_policy_attachment.cni,
    aws_iam_role_policy_attachment.ecr_pull,
  ]
}

# --- OIDC provider for IRSA (create it) ---
# Read cluster to get OIDC issuer
data "aws_eks_cluster" "this" {
  name = aws_eks_cluster.this.name
}

# Fetch TLS cert to compute thumbprint
data "tls_certificate" "oidc" {
  url = data.aws_eks_cluster.this.identity[0].oidc[0].issuer
}

# Create IAM OIDC provider
resource "aws_iam_openid_connect_provider" "this" {
  url             = data.aws_eks_cluster.this.identity[0].oidc[0].issuer
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.oidc.certificates[0].sha1_fingerprint]
}
