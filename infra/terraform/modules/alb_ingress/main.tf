# Create the Kubernetes ServiceAccount with IRSA annotation pointing to the IAM role that was created in the iam module.
resource "kubernetes_service_account" "controller" {
  metadata {
    name      = var.service_account_name
    namespace = var.namespace
    annotations = {
      "eks.amazonaws.com/role-arn" = var.controller_role_arn
    }
    labels = { "app.kubernetes.io/name" = "aws-load-balancer-controller" }
  }
}

# Install the AWS Load Balancer Controller via Helm
resource "helm_release" "alb" {
  name       = "aws-load-balancer-controller"
  namespace  = var.namespace
  repository = "https://aws.github.io/eks-charts"
  chart      = "aws-load-balancer-controller"
  version    = "1.8.1"

  values = [
    yamlencode({
      clusterName = var.cluster_name
      region      = var.region
      vpcId       = var.vpc_id
      serviceAccount = {
        create = false
        name   = kubernetes_service_account.controller.metadata[0].name
        annotations = {
          "eks.amazonaws.com/role-arn" = var.controller_role_arn
        }
      }
      enableShield = false
      enableWaf    = false
    })
  ]

  depends_on = [kubernetes_service_account.controller]
}
