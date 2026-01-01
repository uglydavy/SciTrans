# Configuration Guide

This document explains how to configure SciTrans for production use.

## API Keys and Secrets

### Environment Variables

SciTrans uses environment variables for API keys and configuration. **Never commit API keys to git.**

1. **Copy the example file:**
   ```bash
   cp env.example .env
   ```

2. **Edit `.env` with your API keys:**
   ```bash
   # Required for production backends
   ANTHROPIC_API_KEY=sk-ant-api03-...
   OPENAI_API_KEY=sk-proj-...
   ```

3. **Load environment variables:**
   ```bash
   source .env
   # or use direnv: direnv allow
   ```

### Backend Configuration

#### Anthropic (Claude) - Recommended
```bash
export ANTHROPIC_API_KEY="sk-ant-api03-..."
```

Usage:
```bash
scitrans translate --in doc.pdf --out doc_fr.pdf --backend anthropic
```

#### OpenAI (GPT models)
```bash
export OPENAI_API_KEY="sk-proj-..."
# Optional: custom endpoint
export OPENAI_BASE_URL="https://api.openai.com/v1"
```

Usage:
```bash
scitrans translate --in doc.pdf --out doc_fr.pdf --backend openai --model gpt-4
```

#### Ollama (Local)
```bash
# Optional: if authentication is required
export OLLAMA_API_KEY="..."
# Optional: custom endpoint
export OLLAMA_BASE_URL="http://localhost:11434"
```

Usage:
```bash
scitrans translate --in doc.pdf --out doc_fr.pdf --backend ollama --model llama2
```

#### Cascade Free (Default)
No API keys required. Combines multiple free models with reranking.

Usage:
```bash
scitrans translate --in doc.pdf --out doc_fr.pdf --backend cascade_free
```

## Output Configuration

### Output Directory
Default: `./outputs`

Override with:
```bash
scitrans translate --in doc.pdf --out doc_fr.pdf --artifacts ./my_outputs
```

Or set environment variable:
```bash
export SCITRANS_OUTPUT_DIR="./my_outputs"
```

### Cache Directory
Default: `./outputs/.cache`

Cache significantly speeds up repeated translations (5-20× faster).

Disable caching:
```bash
scitrans translate --in doc.pdf --out doc_fr.pdf --no-cache
```

## Translation Configuration

### Quality Settings

**High quality (default):**
```bash
scitrans translate --in doc.pdf --out doc_fr.pdf \
  --n-candidates 3 \
  --context 2 \
  --math-aware \
  --preserve-tables
```

**Fast mode (lower quality):**
```bash
scitrans translate --in doc.pdf --out doc_fr.pdf \
  --n-candidates 1 \
  --context 0 \
  --no-rerank
```

**Strict mode (for production):**
```bash
scitrans translate --in doc.pdf --out doc_fr.pdf \
  --n-candidates 5 \
  --context 3 \
  --no-cache  # always translate fresh
```

### Feature Toggles

| Flag | Default | Description |
|------|---------|-------------|
| `--math-aware` | ON | Preserve equation geometry |
| `--preserve-tables` | ON | Skip table translation (safer) |
| `--n-candidates` | 3 | Number of translation candidates |
| `--context` | 2 | Previous blocks for context |
| `--no-cache` | OFF | Disable translation cache |
| `--no-rerank` | OFF | Disable candidate reranking |
| `--no-retry` | OFF | Disable automatic retry |

## Logging and Debugging

### Verbose Mode
```bash
# Add verbosity (when implemented)
scitrans translate --in doc.pdf --out doc_fr.pdf -v
```

### Artifact Inspection
All runs produce artifacts in `outputs/<pdf_stem>/`:
- `parsed.json` — PDF structure
- `masked.json` — Masked content (math/code protected)
- `translations.json` — Translation results
- `pre_scores.json` — Complexity scores
- `post_scores.json` — Quality scores
- `health_scores.json` — Block health diagnostics
- `report.json` — Summary report

### Debug Failed Blocks
```bash
# Check health scores
cat outputs/mydoc/health_scores.json | jq '.[] | select(.ok == false)'

# Repair failed blocks
scitrans repair --in mydoc.pdf --out mydoc_repaired.pdf --artifacts outputs/mydoc --backend anthropic
```

## Security Best Practices

### 1. Never Commit Secrets
- `.env` is in `.gitignore`
- Use environment variables or secret managers
- Rotate keys regularly

### 2. Use Pre-commit Hooks
```bash
pip install pre-commit
pre-commit install
```

Pre-commit will:
- Detect private keys
- Block large files
- Enforce formatting

### 3. Production Deployment
For production environments:
- Use secret managers (AWS Secrets Manager, HashiCorp Vault, etc.)
- Rotate API keys monthly
- Monitor API usage and costs
- Set rate limits
- Enable audit logging

## Troubleshooting

### API Key Not Found
```
Error: ANTHROPIC_API_KEY not set
```

**Solution:**
```bash
export ANTHROPIC_API_KEY="sk-ant-api03-..."
```

### Permission Errors
```
PermissionError: [Errno 1] Operation not permitted
```

**Solution:**
- Check file permissions: `ls -la`
- Ensure output directory is writable
- Run without `sudo` (use virtual environment)

### Cache Issues
```
Translation seems stale
```

**Solution:**
```bash
# Clear cache
rm -rf outputs/.cache

# Or disable caching
scitrans translate --in doc.pdf --out doc_fr.pdf --no-cache
```

## Advanced Configuration

### Custom Backend Endpoints

For OpenAI-compatible gateways:
```bash
export OPENAI_BASE_URL="https://custom-gateway.com/v1"
export OPENAI_API_KEY="custom-key"
```

### Custom Assets Directory
```bash
export SCITRANS_ASSETS_DIR="./custom_assets"
```

### Glossary Files
Create a JSON glossary:
```json
{
  "LLM": "LLM",
  "PDF": "PDF",
  "neural network": "réseau neuronal"
}
```

Use in CLI (when implemented):
```bash
scitrans translate --in doc.pdf --out doc_fr.pdf --glossary ./terms.json
```

---

**For more information:**
- README.md — Overview and quick start
- BENCHMARKS.md — Performance and quality metrics
- PRODUCTION_READINESS_CHECKLIST.md — Deployment checklist

