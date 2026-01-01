# Translation Backends

SciTrans supports multiple translation backends, from free/local to premium paid services.

## Quick Reference

| Backend | Quality | Cost | Setup Difficulty | Speed |
|---------|---------|------|------------------|-------|
| **Anthropic** | ★★★★★ | $$$ | Easy | Fast |
| **OpenAI** | ★★★★★ | $$$ | Easy | Fast |
| **HuggingFace** | ★★★☆☆ | Free-$$ | Medium | Medium |
| **Google Free** | ★★☆☆☆ | Free | None | Slow |
| **Ollama** | ★★★☆☆ | Free | Hard | Medium-Slow |
| **Dummy** | ☆☆☆☆☆ | Free | None | Instant |

## 1. Anthropic (Claude) — Recommended for Production

**Best for:** Production use, high-quality scientific translation

```bash
# Setup
export ANTHROPIC_API_KEY="sk-ant-..."

# Usage
scitrans translate \
  --in paper.pdf \
  --out paper_fr.pdf \
  --backend anthropic \
  --model claude-3-5-sonnet-20241022
```

**Available Models:**
- `claude-3-5-sonnet-20241022` (recommended, best quality/speed)
- `claude-3-5-haiku-20241022` (faster, slightly lower quality)
- `claude-3-opus-20240229` (highest quality, slower)

**Pros:**
- Excellent at scientific text
- Strong math/LaTeX preservation
- Good at following complex instructions (glossary, formatting)
- 200K context window

**Cons:**
- Paid (but reasonable pricing)
- Requires API key

## 2. OpenAI (GPT) / Cascade — Alternative Premium

**Best for:** Production use with OpenAI credits or Cascade/TogetherAI gateways

```bash
# Setup
export OPENAI_API_KEY="sk-..."

# Usage (OpenAI)
scitrans translate \
  --in paper.pdf \
  --out paper_fr.pdf \
  --backend openai \
  --model gpt-4o

# Usage (Cascade or other OpenAI-compatible gateway)
export OPENAI_BASE_URL="https://api.cascade.com/v1"
scitrans translate \
  --in paper.pdf \
  --out paper_fr.pdf \
  --backend openai \
  --model claude-3-5-sonnet
```

**Available Models (OpenAI):**
- `gpt-4o` (recommended)
- `gpt-4-turbo`
- `gpt-3.5-turbo` (faster, lower quality)

**Pros:**
- Excellent quality
- Fast inference
- Wide availability (OpenAI, Cascade, TogetherAI, etc.)
- Supports multi-candidate generation

**Cons:**
- Paid
- May be less focused on scientific text than Claude

## 3. HuggingFace — Free/Paid Tier

**Best for:** Budget-conscious users, experimentation

```bash
# Setup (optional for free tier)
export HUGGINGFACE_API_KEY="hf_..."

# Usage with default model (opus-mt-en-fr)
scitrans translate \
  --in paper.pdf \
  --out paper_fr.pdf \
  --backend huggingface

# Usage with custom model
scitrans translate \
  --in paper.pdf \
  --out paper_fr.pdf \
  --backend huggingface \
  --model facebook/nllb-200-3.3B
```

**Recommended Models:**
- `Helsinki-NLP/opus-mt-en-fr` (default, En→Fr)
- `Helsinki-NLP/opus-mt-fr-en` (Fr→En)
- `facebook/nllb-200-3.3B` (multilingual, requires endpoints)

**Pros:**
- Free tier available
- Many open-source models
- Can use custom endpoints for better performance

**Cons:**
- Free tier is rate-limited and slow
- Quality varies by model
- May struggle with complex scientific text
- Placeholder preservation less reliable

## 4. Google Translate (Free) — Testing Only

**Best for:** Quick testing, low-stakes translation

```bash
# No setup required

# Usage
scitrans translate \
  --in paper.pdf \
  --out paper_fr.pdf \
  --backend google
```

**Pros:**
- No API key required
- Free
- Fast for short texts

**Cons:**
- Rate-limited (may fail on large documents)
- Unreliable (uses unofficial API that may break)
- Poor at preserving formatting
- Weak placeholder preservation
- Not recommended for production

## 5. Ollama — Local Models

**Best for:** Privacy-conscious users, offline translation, experimentation

```bash
# Setup
# 1. Install Ollama: https://ollama.ai/
# 2. Pull a model: ollama pull llama3.2

# Usage
scitrans translate \
  --in paper.pdf \
  --out paper_fr.pdf \
  --backend ollama \
  --model llama3.2
```

**Recommended Models:**
- `llama3.2` (good quality, 3B params)
- `mistral` (good for translation)
- `aya` (multilingual specialist)

**Pros:**
- Free
- Runs locally (privacy, no API limits)
- Offline capable
- No data sent to third parties

**Cons:**
- Requires local setup + model download
- Slower than cloud APIs
- Quality depends on model size
- Requires decent hardware (8GB+ RAM recommended)

## 6. Dummy — Testing Only

**Best for:** Testing pipeline without actual translation

```bash
# Usage
scitrans translate \
  --in paper.pdf \
  --out paper_fr.pdf \
  --backend dummy
```

**Behavior:** Returns input text unchanged (identity function)

**Use cases:**
- Testing pipeline without API costs
- Verifying parsing/rendering work correctly
- Debugging layout issues

## Backend Comparison for Scientific PDFs

### English → French Translation Quality

| Backend | Math Preservation | Format Preservation | Terminology | Speed |
|---------|-------------------|---------------------|-------------|-------|
| Anthropic | ★★★★★ | ★★★★★ | ★★★★★ | Fast |
| OpenAI | ★★★★★ | ★★★★☆ | ★★★★☆ | Fast |
| HuggingFace | ★★★☆☆ | ★★☆☆☆ | ★★☆☆☆ | Medium |
| Google Free | ★★☆☆☆ | ★☆☆☆☆ | ★★☆☆☆ | Slow |
| Ollama | ★★★☆☆ | ★★★☆☆ | ★★★☆☆ | Slow |

### Cost Estimates (1000 pages)

- **Anthropic:** ~$10-50 (depending on page complexity)
- **OpenAI:** ~$15-60
- **HuggingFace Free:** $0 (but slow and rate-limited)
- **HuggingFace Endpoints:** ~$5-20
- **Google Free:** $0 (may fail on large docs)
- **Ollama:** $0 (+ hardware costs)

## Advanced: Custom Backend

You can implement your own backend by following the `TranslationBackend` protocol:

```python
from scitrans.translation.backends.base import TranslateRequest, TranslateResult

class MyCustomBackend:
    name = "custom"
    
    def translate(self, req: TranslateRequest) -> TranslateResult:
        # Your translation logic here
        translated = my_translation_function(req.text)
        
        return TranslateResult(
            candidates=[translated],
            model="my-model",
            backend=self.name,
            meta={"custom_info": "..."},
        )
```

Then register it in `scitrans/cli/main.py`.

## Recommendations

### For Production (High Quality Required)
1. **Anthropic** (claude-3-5-sonnet) — Best overall
2. **OpenAI** (gpt-4o) — Good alternative

### For Budget-Conscious Users
1. **Ollama** (llama3.2) — Best free option if you have hardware
2. **HuggingFace** (with paid endpoints) — Good balance of cost/quality

### For Quick Testing
1. **Dummy** — Zero cost, instant
2. **Google Free** — Quick and dirty translation

### For Privacy/Offline
1. **Ollama** — Only option for completely offline translation

