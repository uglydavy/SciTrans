# Production Readiness Checklist

This checklist ensures SciTrans is ready for production deployment and thesis defense.

## ✅ Repository Hygiene

- [ ] `.gitignore` contains all banned patterns (`.venv`, `.idea`, caches, etc.)
- [ ] No banned artifacts are tracked by git: `git ls-files | grep -E '\.venv|__pycache__|\.pyc'` returns empty
- [ ] `MANIFEST.in` properly prunes banned directories
- [ ] Hygiene check passes: `python scripts/check_repo_hygiene.py --root .`
- [ ] No secrets committed: `git log --all | grep -i 'api_key'` returns no matches
- [ ] `.env` is gitignored and not tracked

## ✅ Build and Packaging

- [ ] `python -m build` succeeds without errors
- [ ] Built sdist contains no banned artifacts:
  ```bash
  tar -tzf dist/*.tar.gz | grep -E '\.venv|__pycache__|\.pyc|outputs|previews' || echo "Clean"
  ```
- [ ] Built wheel installs cleanly:
  ```bash
  pip install dist/*.whl
  scitrans --version
  ```
- [ ] Package includes required assets (fonts): `tar -tzf dist/*.tar.gz | grep '\.ttf'`

## ✅ Code Quality

- [ ] All tests pass: `pytest tests/ -v`
- [ ] Test coverage ≥ 80%: `pytest --cov=scitrans --cov-report=term`
- [ ] Linting passes: `ruff check .`
- [ ] Formatting is consistent: `ruff format --check .`
- [ ] No critical mypy errors: `mypy scitrans/` (optional but recommended)
- [ ] Pre-commit hooks installed and passing:
  ```bash
  pip install pre-commit
  pre-commit install
  pre-commit run --all-files
  ```

## ✅ CI/CD

- [ ] CI workflow exists: `.github/workflows/ci.yml`
- [ ] CI runs on push to main/develop
- [ ] CI includes: hygiene check, lint, tests, build
- [ ] CI tests multiple Python versions (3.9-3.13)
- [ ] CI artifacts (dist) are uploaded
- [ ] CI integration test passes (dummy backend translation)

## ✅ Documentation

- [ ] README.md is up-to-date and accurate
- [ ] QUICK_START.md has working examples
- [ ] CONFIGURATION.md documents all env vars
- [ ] BENCHMARKS.md explains how to run benchmarks
- [ ] All CLI commands documented with `--help`
- [ ] Known limitations are documented
- [ ] env.example exists and is up-to-date

## ✅ Security

- [ ] API keys loaded from environment variables only
- [ ] No hardcoded secrets in code
- [ ] Pre-commit hook detects private keys
- [ ] Large files blocked (>1MB) by pre-commit
- [ ] Logs never print API keys or secrets
- [ ] Error messages don't leak sensitive info

## ✅ Translation Quality

- [ ] Default renderer is explicitly defined in config
- [ ] Math-safe rendering is enabled by default
- [ ] No text overlap regressions:
  ```bash
  scitrans translate --in test_pdfs/02_math_equations.pdf --out test_math.pdf --backend dummy
  # Visually inspect test_math.pdf for overlaps
  ```
- [ ] Masked tokens survive round-trip:
  ```bash
  cat outputs/02_math_equations/masked.json | grep '⟦'
  cat outputs/02_math_equations/translations.json | grep '⟦'
  ```
- [ ] Health scoring identifies issues:
  ```bash
  cat outputs/02_math_equations/health_scores.json | jq '.[] | select(.ok == false)'
  ```

## ✅ Robustness

- [ ] Missing translations logged clearly with block IDs
- [ ] Mask restore failures trigger retries
- [ ] Strict mode aborts on unrecoverable errors
- [ ] CLI returns non-zero exit code on failures
- [ ] Repair workflow works:
  ```bash
  scitrans repair --in test.pdf --out test_repaired.pdf --artifacts outputs/test --backend dummy
  ```

## ✅ Performance

- [ ] Translation caching works (5-20× speedup):
  ```bash
  time scitrans translate --in test.pdf --out test1.pdf --backend dummy
  time scitrans translate --in test.pdf --out test2.pdf --backend dummy  # Should be much faster
  ```
- [ ] Benchmarks run successfully:
  ```bash
  make bench
  ls experiments/results/benchmarks/summary.{json,csv}
  ```
- [ ] Large PDFs (50+ pages) complete without crashing
- [ ] Memory usage is reasonable (<2GB for typical documents)

## ✅ Integration

- [ ] CLI works end-to-end:
  ```bash
  scitrans translate --in test_pdfs/01_simple_text.pdf --out test_out.pdf --backend dummy
  test -f test_out.pdf && test -f outputs/01_simple_text/report.json
  ```
- [ ] All backends initialize correctly (when keys are set):
  ```bash
  scitrans translate --in test.pdf --out test_anthropic.pdf --backend anthropic
  scitrans translate --in test.pdf --out test_openai.pdf --backend openai
  scitrans translate --in test.pdf --out test_cascade.pdf --backend cascade_free
  ```
- [ ] Repair command works:
  ```bash
  scitrans repair --in test.pdf --out repaired.pdf --artifacts outputs/test --backend dummy
  ```

## ✅ Thesis-Specific

- [ ] All experiments run successfully: `make experiments`
- [ ] Benchmark visualizations generate: `make viz-bench` (requires matplotlib)
- [ ] Aggregated results exist: `experiments/results/aggregated_results.json`
- [ ] Thesis figures are publication-quality (300 DPI PNG)
- [ ] Human evaluation template generated
- [ ] Verification checklist passes: `python experiments/verify_thesis_readiness.py`
- [ ] All claimed features are verifiable with tests

## ✅ Deployment

- [ ] Installation works on clean machine:
  ```bash
  git clone <repo>
  cd SciTrans
  python -m venv .venv
  source .venv/bin/activate
  pip install -e ".[dev]"
  pytest
  ```
- [ ] README has accurate install instructions
- [ ] Dependencies are pinned or have reasonable constraints
- [ ] Works on macOS and Linux (Windows optional)
- [ ] PyPI metadata is complete (if publishing):
  ```bash
  twine check dist/*
  ```

## ✅ Final Verification Commands

Run these commands to verify production readiness:

```bash
# 1. Hygiene
python scripts/check_repo_hygiene.py --root .

# 2. Tests
pytest tests/ -v

# 3. Lint
ruff check . && ruff format --check .

# 4. Build
python -m build

# 5. Install from wheel
pip install --force-reinstall dist/*.whl

# 6. Integration test
python -c "import fitz; doc=fitz.open(); p=doc.new_page(width=300,height=200); p.insert_text((50,80),'Test',fontsize=12); doc.save('test.pdf'); doc.close()"
scitrans translate --in test.pdf --out test_out.pdf --backend dummy
test -f test_out.pdf && test -f outputs/test/report.json && echo "✅ Integration test passed"

# 7. Benchmarks
make bench

# 8. Pre-commit
pre-commit run --all-files
```

---

## Acceptance Criteria Summary

**All checks must pass before:**
- Thesis defense
- Public repository release
- Production deployment
- PyPI publication

**Minimum Requirements:**
- ✅ Hygiene check passes
- ✅ All tests pass (≥80% coverage)
- ✅ Linting passes
- ✅ Build succeeds with clean artifacts
- ✅ CLI integration test passes
- ✅ No secrets committed

**Recommended for Production:**
- ✅ CI/CD pipeline active
- ✅ Pre-commit hooks installed
- ✅ Benchmarks completed
- ✅ Security audit done
- ✅ Documentation complete

---

**Status Tracking:**

Update this checklist as you progress. Mark items with `[x]` when complete.

**Last Updated:** 2025-01-30  
**Version:** 1.0.0  
**Author:** Franck Davy

