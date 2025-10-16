SHELL := /bin/bash

# ---- Tools ----
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
BLACK := $(VENV)/bin/black
RUFF := $(VENV)/bin/ruff
PRECOMMIT := $(VENV)/bin/pre-commit
PYTEST := $(VENV)/bin/pytest

.PHONY: help
help:
	@echo "Targets:"
	@echo "  make init   # create venv + dev tools + git hooks"
	@echo "  make fmt    # format (black + ruff format)"
	@echo "  make lint   # lint (ruff check + black --check)"
	@echo "  make test   # run tests (if any)"

# Bootstrap venv + dev tools
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
	@if compgen -G "services/**/tests/*.py" > /dev/null; then \
		$(PYTEST) -q ; \
	else \
		echo "No tests found; skipping."; \
	fi
