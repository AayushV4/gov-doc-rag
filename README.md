# Gov-Doc RAG on AWS (Bedrock + Textract + Translate)

Production-oriented, bilingual (EN/FR) Retrieval-Augmented Generation system for Canadian public-sector PDFs. Infra via Terraform, runtime on EKS, CI/CD with GitHub Actions (OIDC), observability via CloudWatch + OTel, cost guardrails via AWS Budgets. Vector DB defaults to Pinecone (Milvus optional on EKS).

## Quick start (Phase 0)

**Prereqs** (install before proceeding):
- Python 3.11+, `pip`, `git`
- Docker
- Node 20+ (for `/services/web` later)
- Terraform, kubectl, Helm, AWS CLI (used from Phase 1 onward; optional for Phase 0)

```bash
# clone and bootstrap tools
git clone https://github.com/<your-org>/gov-doc-rag.git
cd gov-doc-rag

make init           # creates .venv, installs black/ruff/pre-commit/pytest, installs git hooks
make fmt && make lint
