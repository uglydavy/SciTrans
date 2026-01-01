.PHONY: help install install-all test test-cov lint format clean setup-keys docs

help:  ## Show this help message
	@echo "SciTrans - Makefile Commands"
	@echo "============================"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install package in development mode
	python3 -m pip install -U pip setuptools wheel
	python3 -m pip install -e ".[dev]"

install-all:  ## Install with all optional dependencies
	python3 -m pip install -U pip setuptools wheel
	python3 -m pip install -e ".[all]"

reinstall:  ## Reinstall package after code changes (fixes scitrans command)
	python3 -m pip install --force-reinstall --no-deps -e .

test:  ## Run tests
	pytest tests/ -v

test-cov:  ## Run tests with coverage
	pytest tests/ -v --cov=scitrans --cov-report=html --cov-report=term

test-fast:  ## Run fast tests (skip slow integration tests)
	pytest tests/ -v -m "not slow"

lint:  ## Run linters (ruff, mypy)
	ruff check scitrans/ tests/
	mypy scitrans/

format:  ## Format code with ruff
	ruff format scitrans/ tests/
	ruff check --fix scitrans/ tests/

clean:  ## Clean up generated files
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .ruff_cache
	rm -rf htmlcov/
	rm -rf outputs/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

setup-keys:  ## Run interactive API key setup
	python3 scripts/setup_api_keys.py

create-test-pdfs:  ## Create 10 test PDFs
	python3 scripts/create_test_pdfs.py

demo:  ## Run demo translation (dummy backend)
	@echo "Creating test PDF..."
	@python3 -c "import fitz; doc=fitz.open(); p=doc.new_page(width=300, height=200); p.insert_text((50,80),'Hello World',fontsize=12); p.insert_text((50,100),'This is a test.',fontsize=12); doc.save('test_input.pdf'); doc.close()"
	@echo "Translating..."
	scitrans translate --in test_input.pdf --out test_output.pdf --backend dummy
	@echo "Done! Check test_output.pdf and outputs/test_input/"

test-all-pdfs:  ## Test translation on all test PDFs
	@echo "Testing all PDFs with dummy backend..."
	@for pdf in test_pdfs/*.pdf; do \
		echo "Testing $$pdf..."; \
		scitrans translate --in "$$pdf" --out "outputs/$$(basename $$pdf .pdf)_output.pdf" --backend dummy --no-cache; \
	done
	@echo "Done! Check outputs/ directory"

demo-anthropic:  ## Run demo with Anthropic backend (requires API key)
	@echo "Creating test PDF..."
	@python3 -c "import fitz; doc=fitz.open(); p=doc.new_page(width=300, height=200); p.insert_text((50,80),'Hello World',fontsize=12); p.insert_text((50,100),'This is a test.',fontsize=12); doc.save('test_input.pdf'); doc.close()"
	@echo "Translating with Anthropic..."
	scitrans translate --in test_input.pdf --out test_output_anthropic.pdf --backend anthropic --model claude-3-5-sonnet-20241022
	@echo "Done! Check test_output_anthropic.pdf"

check:  ## Run all checks (lint + test)
	@$(MAKE) lint
	@$(MAKE) test

docs-serve:  ## Serve documentation locally (if using mkdocs)
	@echo "Documentation files are in docs/"
	@echo "See README.md, QUICK_START.md, IMPLEMENTATION_SUMMARY.md"

version:  ## Show version
	@python -c "from scitrans import __version__; print(__version__)"

experiments:  ## Run all thesis experiments
	bash experiments/run_all_experiments.sh

analyze:  ## Analyze experimental results
	python3 experiments/aggregate_results.py
	python3 experiments/create_thesis_figures.py

viz:  ## Create all thesis visualizations
	python3 experiments/create_thesis_figures.py

viz-bench:  ## Visualize benchmark results
	python3 scripts/visualize_benchmarks.py

backends:  ## Show available backends
	@echo "Available backends:"
	@echo "  - cascade_free (DEFAULT: multiple free models combined, recommended)"
	@echo "  - anthropic (Claude, requires ANTHROPIC_API_KEY, production quality)"
	@echo "  - openai (GPT, Cascade, requires OPENAI_API_KEY)"
	@echo "  - google (free Google Translate, no key required)"
	@echo "  - huggingface (HF models, optional HUGGINGFACE_API_KEY)"
	@echo "  - ollama (local models, requires Ollama running)"
	@echo "  - dummy (testing only, identity translation)"

preview:  ## Generate PDF preview comparison
	@echo "Usage: make preview SOURCE=input.pdf TRANSLATED=output.pdf"
	@if [ -z "$(SOURCE)" ] || [ -z "$(TRANSLATED)" ]; then \
		echo "Error: SOURCE and TRANSLATED required"; \
		echo "Example: make preview SOURCE=test.pdf TRANSLATED=test_fr.pdf"; \
		exit 1; \
	fi
	python3 scripts/preview_pdfs.py --source "$(SOURCE)" --translated "$(TRANSLATED)"
	@echo "✓ Preview saved to: previews/comparison_page_0.png"

bench:  ## Run benchmarks on test_pdfs with free backends
	python3 scripts/run_benchmarks.py

bench-paid:  ## Run benchmarks including paid backends if keys set
	python3 scripts/run_benchmarks.py --include-paid

bench-all:  ## Run benchmarks and generate visualizations
	@$(MAKE) bench
	@$(MAKE) viz-bench

