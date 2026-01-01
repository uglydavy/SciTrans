# API Keys Setup Guide

This guide shows you how to configure API keys for all SciTrans backends.

## Quick Setup Script

The easiest way is to use the interactive setup script:

```bash
python3 scripts/setup_api_keys.py
```

Or manually create `.env` file (see below).

---

## Manual Setup

### Step 1: Create .env File

```bash
# Copy template
cp env.example .env

# Edit .env with your keys
nano .env
```

### Step 2: Add Your API Keys

Based on your provided keys, your `.env` file should look like:

```bash
# OpenAI (GPT models)
OPENAI_API_KEY=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

# Anthropic (Claude) - using qidianai.xyz endpoint
ANTHROPIC_API_KEY=sk-FScC15a0Z3ytYASnEa5cEf472d1443978d43D6C37628Ed6a
ANTHROPIC_BASE_URL=https://api.qidianai.xyz

# Google Translate
GOOGLE_API_KEY=AIzaSyClRFY53cq3_R7gLILfNj2Jcerlzc3Yhn0

# Ollama (local)
OLLAMA_API_KEY=4d1db5aec4ea461597630de5ed70577f.RM_rfzxhCeSJ5X36Kz8cjSn-
OLLAMA_BASE_URL=http://localhost:11434
```

### Step 3: Load Environment Variables

**Option A: Load from .env file**
```bash
source .env
```

**Option B: Export directly**
```bash
export OPENAI_API_KEY="sk-proj-..."
export ANTHROPIC_API_KEY="sk-FSc..."
export ANTHROPIC_BASE_URL="https://api.qidianai.xyz"
export GOOGLE_API_KEY="AIza..."
export OLLAMA_API_KEY="4d1d..."
export OLLAMA_BASE_URL="http://localhost:11434"
```

**Option C: Add to shell profile (persistent)**

Add to `~/.zshrc` or `~/.bashrc`:
```bash
# SciTrans API Keys
export OPENAI_API_KEY="sk-proj-..."
export ANTHROPIC_API_KEY="sk-FSc..."
export ANTHROPIC_BASE_URL="https://api.qidianai.xyz"
export GOOGLE_API_KEY="AIza..."
export OLLAMA_API_KEY="4d1d..."
export OLLAMA_BASE_URL="http://localhost:11434"
```

Then reload:
```bash
source ~/.zshrc  # or source ~/.bashrc
```

---

## Backend-Specific Configuration

### Anthropic (Claude) with QidianAI

Your Anthropic key is from [qidianai.xyz](https://qidianai.xyz), which provides Claude API access through a proxy.

**Configuration:**
```bash
export ANTHROPIC_API_KEY="sk-FScC15a0Z3ytYASnEa5cEf472d1443978d43D6C37628Ed6a"
export ANTHROPIC_BASE_URL="https://api.qidianai.xyz"
```

**Usage:**
```bash
scitrans translate --in doc.pdf --out doc_fr.pdf --backend anthropic
```

**Available models** (per [qidianai.xyz docs](https://qidianai.xyz/qidian/index.html)):
- `claude-3-5-sonnet-20241022` (recommended)
- `claude-3-5-sonnet-20240620`
- `claude-3-opus-20240229`
- `claude-3-haiku-20240307`
- `claude-2.1`, `claude-2.0`

### OpenAI (GPT models)

**Configuration:**
```bash
export OPENAI_API_KEY="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"
```

**Usage:**
```bash
scitrans translate --in doc.pdf --out doc_fr.pdf --backend openai --model gpt-4
```

### Google Translate

**Configuration:**
```bash
export GOOGLE_API_KEY="AIzaSyClRFY53cq3_R7gLILfNj2Jcerlzc3Yhn0"
```

**Usage:**
```bash
scitrans translate --in doc.pdf --out doc_fr.pdf --backend google
```

### Ollama (Local)

Ollama installed at: `/Users/kv.kn/.ollama/models`

**Configuration:**
```bash
export OLLAMA_API_KEY="4d1db5aec4ea461597630de5ed70577f.RM_rfzxhCeSJ5X36Kz8cjSn-"
export OLLAMA_BASE_URL="http://localhost:11434"
```

**Usage:**
```bash
# Ensure Ollama is running
ollama serve  # In separate terminal

# Then translate
scitrans translate --in doc.pdf --out doc_fr.pdf --backend ollama --model llama2
```

---

## Testing Backend Connections

### Test All Backends

```bash
# Load environment variables
source .env  # or export commands above

# Test OpenAI
python3 -c "import os; from scitrans.translation.backends.openai_backend import OpenAIBackend; b=OpenAIBackend(); print('OpenAI:', 'OK' if os.getenv('OPENAI_API_KEY') else 'Missing key')"

# Test Anthropic
python3 -c "import os; from scitrans.translation.backends.anthropic_backend import AnthropicBackend; b=AnthropicBackend(); print('Anthropic:', 'OK' if os.getenv('ANTHROPIC_API_KEY') else 'Missing key')"

# Test Google
python3 -c "import os; from scitrans.translation.backends.google_backend import GoogleTranslateBackend; b=GoogleTranslateBackend(); print('Google:', 'OK' if os.getenv('GOOGLE_API_KEY') else 'Will use free tier')"

# Test Ollama
python3 -c "import os; from scitrans.translation.backends.ollama_backend import OllamaBackend; b=OllamaBackend(); print('Ollama:', 'OK' if os.getenv('OLLAMA_API_KEY') else 'No key')"
```

### Run Backend Tests

```bash
# Export keys first
source .env

# Run backend tests (will no longer skip)
python3 -m pytest tests/test_backends.py -v
```

---

## Security Best Practices

### 1. Never Commit .env
- `.env` is in `.gitignore` — never commit it
- Pre-commit hooks detect private keys
- Use environment variables for production

### 2. Rotate Keys Regularly
- Change keys monthly (recommended)
- Revoke immediately if exposed
- Use separate keys for dev/prod

### 3. Use Secret Managers (Production)
- AWS Secrets Manager
- HashiCorp Vault
- Azure Key Vault
- GCP Secret Manager

### 4. Monitor Usage
- Check API usage regularly
- Set up billing alerts
- Monitor for unusual activity

---

## Troubleshooting

### "API key not found"
```bash
# Verify environment variable is set
echo $ANTHROPIC_API_KEY
echo $OPENAI_API_KEY

# If empty, reload .env
source .env
```

### "Connection refused" (Ollama)
```bash
# Start Ollama server
ollama serve

# In another terminal, verify it's running
curl http://localhost:11434/api/tags
```

### "Rate limit exceeded"
- Wait a few minutes
- Check your API quota/billing
- Use caching to reduce API calls: `--no-cache=False` (default)

### Custom Anthropic endpoint not working
```bash
# Verify base URL is set
echo $ANTHROPIC_BASE_URL
# Should show: https://api.qidianai.xyz

# If not set:
export ANTHROPIC_BASE_URL="https://api.qidianai.xyz"
```

---

## Verification Commands

After setting up keys, verify all backends work:

```bash
# 1. Load keys
source .env

# 2. Create test PDF
python3 -c "import fitz; doc=fitz.open(); p=doc.new_page(width=300,height=200); p.insert_text((50,80),'Hello world',fontsize=12); doc.save('test.pdf'); doc.close()"

# 3. Test each backend

# Cascade-free (no keys needed)
scitrans translate --in test.pdf --out test_cascade.pdf --backend cascade_free

# Anthropic (qidianai.xyz)
scitrans translate --in test.pdf --out test_anthropic.pdf --backend anthropic

# OpenAI
scitrans translate --in test.pdf --out test_openai.pdf --backend openai --model gpt-4

# Google
scitrans translate --in test.pdf --out test_google.pdf --backend google

# Ollama (ensure server is running)
scitrans translate --in test.pdf --out test_ollama.pdf --backend ollama --model llama2

# 4. Verify outputs
ls test_*.pdf
```

---

## QidianAI Endpoint Details

Per [qidianai.xyz documentation](https://qidianai.xyz/qidian/index.html):

**Base URL:** `https://api.qidianai.xyz`

**Available models:**
- GPT-5, GLM-4.5, GLM-4.6, DeepSeek-V3.1, DeepSeek-V3.2
- Claude-3.5-Sonnet, Claude-3-Opus, Claude-3-Haiku
- Claude-2.1, Claude-2.0

**Authentication:**
```
Authorization: Bearer sk-FScC15a0Z3ytYASnEa5cEf472d1443978d43D6C37628Ed6a
```

**For Anthropic API (via qidianai):**
```bash
export ANTHROPIC_BASE_URL="https://api.qidianai.xyz"
export ANTHROPIC_API_KEY="sk-FScC15a0Z3ytYASnEa5cEf472d1443978d43D6C37628Ed6a"
```

**For OpenAI API (if using qidianai for OpenAI):**
```bash
export OPENAI_BASE_URL="https://api.qidianai.xyz/v1"
export OPENAI_API_KEY="sk-FScC15a0Z3ytYASnEa5cEf472d1443978d43D6C37628Ed6a"
```

---

## Quick Test All Backends

```bash
# Create quick test script
cat > test_all_backends.sh << 'EOF'
#!/bin/bash
source .env
python3 -c "import fitz; doc=fitz.open(); p=doc.new_page(width=300,height=200); p.insert_text((50,80),'Test translation',fontsize=12); doc.save('test.pdf'); doc.close()"

echo "Testing cascade_free..."
python3 -m scitrans.cli.main translate --in test.pdf --out test_cascade.pdf --backend cascade_free

echo "Testing anthropic..."
python3 -m scitrans.cli.main translate --in test.pdf --out test_anthropic.pdf --backend anthropic

echo "Testing openai..."
python3 -m scitrans.cli.main translate --in test.pdf --out test_openai.pdf --backend openai

echo "Testing google..."
python3 -m scitrans.cli.main translate --in test.pdf --out test_google.pdf --backend google

echo "✅ All backends tested"
EOF

chmod +x test_all_backends.sh
bash test_all_backends.sh
```

---

## Contact

Questions? aknk.v@pm.me

