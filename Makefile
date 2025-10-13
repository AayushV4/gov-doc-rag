
---

### `Makefile`
```makefile
SHELL := /bin/bash

# ---- Paths / tools ----
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
BLACK := $(VENV)/bin/black
RUFF := $(VENV)/bin/ruff
PRECOMMIT := $(VENV)/bin/pre-commit
PYTEST := $(VENV)/bin/pytest

# Help text
.PHONY: help
help:
	@echo "Common targets:"
	@echo "  make init        # Create venv, install dev tools, install pre-commit hooks"
	@echo "  make fmt         # Format code (black + ruff format)"
	@echo "  make lint        # Lint (ruff check + black --check)"
	@echo "  make test        # Run tests (if any)"
	@echo "  make tf-init     # Terraform init in infra/terraform"
	@echo "  make tf-apply    # Terraform apply (Phase 1+)"
	@echo "  make tf-destroy  # Terraform destroy (Phase 1+)"
	@echo "  make build       # Build service images if Dockerfiles exist (Phase 5)"
	@echo "  make up          # (reserved for local compose; noop for now)"
	@echo "  make down        # (reserved for local compose; noop for now)"

# ---- Bootstrap ----
$(VENV)/bin/activate:
	python3 -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install \
		black==24.8.0 \
		ruff==0.6.8 \
		pre-commit==3.8.0 \
		pytest==8.2.0

.PHONY: init
init: $(VENV)/bin/activate
	$(PRECOMMIT) install
	@echo "✅ Dev tools installed. Git hooks enabled."

# ---- Code quality ----
.PHONY: fmt
fmt: init
	$(BLACK) .
	$(RUFF) format .

.PHONY: lint
lint: init
	$(RUFF) check .
	$(BLACK) --check .

.PHONY: test
test: init
	@# Run tests if present; do not fail the repo when none exist
	@if compgen -G "services/**/tests/*.py" > /dev/null; then \
		$(PYTEST) -q ; \
	else \
		echo "No tests found; skipping."; \
	fi

# ---- Terraform wrappers (Phase 1+) ----
TF_DIR := infra/terraform

.PHONY: tf-init
tf-init:
	@if [ -d "$(TF_DIR)" ]; then \
		cd $(TF_DIR) && terraform init; \
	else \
		echo "Terraform dir not found: $(TF_DIR)"; exit 1; \
	fi

.PHONY: tf-apply
tf-apply:
	@if [ -d "$(TF_DIR)" ]; then \
		cd $(TF_DIR) && terraform apply -auto-approve; \
	else \
		echo "Terraform dir not found: $(TF_DIR)"; exit 1; \
	fi

.PHONY: tf-destroy
tf-destroy:
	@if [ -d "$(TF_DIR)" ]; then \
		cd $(TF_DIR) && terraform destroy -auto-approve; \
	else \
		echo "Terraform dir not found: $(TF_DIR)"; exit 1; \
	fi

# ---- Container build (Phase 5+) ----
SERVICES := api indexer ingestor web

.PHONY: build
build:
	@for svc in $(SERVICES); do \
		df="services/$$svc/Dockerfile"; \
		if [ -f "$$df" ]; then \
			echo "Building $$svc..."; \
			docker build -t $$svc:dev -f $$df services/$$svc; \
		else \
			echo "Skipping $$svc (no Dockerfile yet)"; \
		fi \
	done

# ---- Local runtime placeholders ----
.PHONY: up
up:
	@echo "Local compose not used. We deploy to EKS in Phase 5. (noop)"

.PHONY: down
down:
	@echo "Local compose not used. We deploy to EKS in Phase 5. (noop)"
