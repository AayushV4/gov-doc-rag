locals {
  sa_ns = "default"
}

# ---------- IRSA trust policy helper ----------
data "aws_iam_policy_document" "irsa_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [var.cluster_oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${replace(var.cluster_oidc_provider_url, "https://", "")}:sub"
      values = [
        "system:serviceaccount:${local.sa_ns}:api",
        "system:serviceaccount:${local.sa_ns}:indexer",
        "system:serviceaccount:${local.sa_ns}:ingestor",
        "system:serviceaccount:kube-system:${var.project}-alb-controller",
        "system:serviceaccount:amazon-cloudwatch:fluentbit"
      ]
    }
  }
}

# ---------- Policies ----------
data "aws_iam_policy_document" "ingestor" {
  statement {
    actions   = ["textract:StartDocumentAnalysis", "textract:GetDocumentAnalysis"]
    resources = ["*"]
  }
  statement {
    actions = ["s3:PutObject", "s3:GetObject", "s3:ListBucket"]
    resources = [
      var.raw_bucket_arn, "${var.raw_bucket_arn}/*",
      var.processed_bucket_arn, "${var.processed_bucket_arn}/*"
    ]
  }
  statement {
    actions   = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"]
    resources = [var.s3_kms_key_arn]
  }

  statement {
    sid = "CloudWatchLogs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogStreams"
    ]
    resources = [
      "arn:aws:logs:${var.region}:*:log-group:/aws/eks/${var.cluster_name}/application/ingestor",
      "arn:aws:logs:${var.region}:*:log-group:/aws/eks/${var.cluster_name}/application/ingestor:*"
    ]
  }
}

data "aws_iam_policy_document" "indexer" {
  statement {
    actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = ["*"]
  }
  statement {
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [var.processed_bucket_arn, "${var.processed_bucket_arn}/*"]
  }
  statement {
    actions   = ["secretsmanager:GetSecretValue", "kms:Decrypt"]
    resources = ["*"]
    condition {
      test     = "StringLike"
      variable = "secretsmanager:ResourceTag/project"
      values   = [var.project]
    }
  }
  statement {
    sid = "CloudWatchLogs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogStreams"
    ]
    resources = [
      "arn:aws:logs:${var.region}:*:log-group:/aws/eks/${var.cluster_name}/application/indexer",
      "arn:aws:logs:${var.region}:*:log-group:/aws/eks/${var.cluster_name}/application/indexer:*"
    ]
  }
}

data "aws_iam_policy_document" "api" {
  statement {
    actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = ["*"]
  }
  statement {
    actions   = ["translate:TranslateText"]
    resources = ["*"]
  }
  statement {
    actions = ["s3:GetObject", "s3:ListBucket"]
    resources = [
      var.processed_bucket_arn, "${var.processed_bucket_arn}/*",
      var.index_bucket_arn, "${var.index_bucket_arn}/*"
    ]
  }
  statement {
    sid = "CloudWatchLogs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogStreams"
    ]
    resources = [
      "arn:aws:logs:${var.region}:*:log-group:/aws/eks/${var.cluster_name}/application/api",
      "arn:aws:logs:${var.region}:*:log-group:/aws/eks/${var.cluster_name}/application/api:*"
    ]
  }
  statement {
    actions   = ["secretsmanager:GetSecretValue", "kms:Decrypt"]
    resources = ["*"]
    condition {
      test     = "StringLike"
      variable = "secretsmanager:ResourceTag/project"
      values   = [var.project]
    }
  }
}

# ---------- Roles ----------
resource "aws_iam_role" "ingestor" {
  name               = "${var.project}-ingestor"
  assume_role_policy = data.aws_iam_policy_document.irsa_trust.json
}
resource "aws_iam_role_policy" "ingestor" {
  role   = aws_iam_role.ingestor.id
  policy = data.aws_iam_policy_document.ingestor.json
}

resource "aws_iam_role" "indexer" {
  name               = "${var.project}-indexer"
  assume_role_policy = data.aws_iam_policy_document.irsa_trust.json
}
resource "aws_iam_role_policy" "indexer" {
  role   = aws_iam_role.indexer.id
  policy = data.aws_iam_policy_document.indexer.json
}

resource "aws_iam_role" "api" {
  name               = "${var.project}-api"
  assume_role_policy = data.aws_iam_policy_document.irsa_trust.json
}
resource "aws_iam_role_policy" "api" {
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api.json
}

# ---------- AWS Load Balancer Controller role ----------
data "aws_iam_policy_document" "alb" {
  statement {
    actions   = ["iam:CreateServiceLinkedRole"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "iam:AWSServiceName"
      values   = ["elasticloadbalancing.amazonaws.com"]
    }
  }
  statement {
    actions = [
      "ec2:CreateSecurityGroup",
      "ec2:DeleteSecurityGroup",
      "ec2:AuthorizeSecurityGroupIngress",
      "ec2:RevokeSecurityGroupIngress",
      "ec2:AuthorizeSecurityGroupEgress",
      "ec2:RevokeSecurityGroupEgress",
      "ec2:Describe*",
      "ec2:ModifyNetworkInterfaceAttribute",
      "ec2:AttachNetworkInterface"
    ]
    resources = ["*"]
  }
  statement {
    actions   = ["elasticloadbalancing:*"]
    resources = ["*"]
  }
  statement {
    actions   = ["iam:CreateServiceLinkedRole", "iam:GetServerCertificate", "iam:ListServerCertificates"]
    resources = ["*"]
  }
}

# ---------- FluentBit CloudWatch Logs policy ----------
data "aws_iam_policy_document" "fluentbit" {
  statement {
    sid = "CloudWatchLogsPut"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role" "alb_controller" {
  name               = "${var.project}-alb-controller"
  assume_role_policy = data.aws_iam_policy_document.irsa_trust.json
}
resource "aws_iam_role_policy" "alb_controller" {
  role   = aws_iam_role.alb_controller.id
  policy = data.aws_iam_policy_document.alb.json
}

# ---------- FluentBit role ----------
resource "aws_iam_role" "fluentbit" {
  name               = "${var.project}-fluentbit"
  assume_role_policy = data.aws_iam_policy_document.irsa_trust.json
}

resource "aws_iam_role_policy" "fluentbit" {
  role   = aws_iam_role.fluentbit.id
  policy = data.aws_iam_policy_document.fluentbit.json
}

# ---------- Optional: GitHub Actions OIDC role (created if enabled) ----------
resource "aws_iam_openid_connect_provider" "github" {
  count           = var.create_github_oidc ? 1 : 0
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

data "aws_iam_policy_document" "gha_assume" {
  count = var.create_github_oidc ? 1 : 0
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github[0].arn]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_org}/${var.github_repo}:*"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "gha_deploy" {
  count              = var.create_github_oidc ? 1 : 0
  name               = "${var.project}-gha-deploy"
  assume_role_policy = data.aws_iam_policy_document.gha_assume[0].json
}

resource "aws_iam_role_policy" "gha_deploy" {
  count = var.create_github_oidc ? 1 : 0
  role  = aws_iam_role.gha_deploy[0].id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      { Effect = "Allow", Action = ["ecr:*"], Resource = "*" },
      { Effect = "Allow", Action = ["eks:*", "iam:PassRole", "sts:AssumeRole"], Resource = "*" },
      { Effect = "Allow", Action = ["s3:*", "kms:*", "secretsmanager:*", "ssm:*"], Resource = "*" }
    ]
  })
}
