# Contributing to SciTrans

Thanks for your interest in contributing to SciTrans-LLMs!

## Development Setup

1. **Clone and setup environment:**
   ```bash
   git clone <repository-url>
   cd SciTrans
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -e ".[dev]"
   ```

2. **Install pre-commit hooks:**
   ```bash
   pip install pre-commit
   pre-commit install
   ```

3. **Run tests:**
   ```bash
   python3 -m pytest tests/ -v
   ```

4. **Run linting:**
   ```bash
   python3 -m ruff check .
   python3 -m ruff format .
   ```

## Development Workflow

### Before committing:
```bash
# Format code
python3 -m ruff format .

# Check linting
python3 -m ruff check .

# Run tests
python3 -m pytest tests/ -v

# Check hygiene
python3 scripts/check_repo_hygiene.py --root .
```

### Making changes:
1. Create a feature branch: `git checkout -b feature/your-feature`
2. Make your changes
3. Add tests for new functionality
4. Update documentation if behavior changed
5. Run all checks (see above)
6. Commit with clear messages
7. Push and create pull request

## Pull Request Checklist

- [ ] No local artifacts committed (`.venv/`, `.idea/`, `__pycache__/`, `*.pyc`, `*.egg-info`, etc.)
- [ ] All tests pass (`python3 -m pytest tests/ -v`)
- [ ] Formatting is consistent (`python3 -m ruff format .`)
- [ ] Linting passes (`python3 -m ruff check .`)
- [ ] New features include tests
- [ ] Documentation updated (README, docstrings, etc.)
- [ ] No API keys or secrets in code
- [ ] Pre-commit hooks pass (`pre-commit run --all-files`)

## Code Style

- Follow PEP 8 (enforced by ruff)
- Use type hints where appropriate
- Add docstrings to public functions/classes
- Keep functions focused and testable
- Prefer explicit over implicit

## Testing Guidelines

- Write tests for new features
- Maintain ≥80% code coverage
- Use descriptive test names: `test_<what>_<when>_<expected>`
- Use fixtures for common setup
- Mark slow tests with `@pytest.mark.slow`

## Documentation

- Update README.md for user-facing changes
- Update relevant docs/ files for architecture changes
- Add inline comments for complex logic
- Keep docstrings up-to-date

## Commit Messages

Use clear, descriptive commit messages:

```
feat: Add table cell-level rendering
fix: Correct placeholder validation logic
docs: Update configuration guide
test: Add math detection tests
refactor: Simplify masking engine
```

## Questions or Issues?

- Check existing documentation in `docs/`
- Open an issue for bugs or feature requests
- Contact: aknk.v@pm.me

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

