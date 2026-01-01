# Enhanced GUI Features

## Overview

The SciTrans GUI has been significantly enhanced with advanced features for professional translation workflows, comprehensive testing, detailed ablation studies, and sophisticated glossary management.

## Table of Contents

1. [Translation Tab Enhancements](#translation-tab-enhancements)
2. [Testing Tab Features](#testing-tab-features)
3. [Ablation Tab Improvements](#ablation-tab-improvements)
4. [Glossary Management](#glossary-management)
5. [Settings & Configuration](#settings--configuration)
6. [Installation](#installation)

---

## Translation Tab Enhancements

### Input Methods

#### **PDF Upload**
- Traditional file upload via drag-and-drop or file browser
- Supports all standard PDF formats
- Immediate file validation

#### **URL Fetching** ⭐ NEW
- Fetch PDFs directly from the internet
- Simply paste a URL (e.g., `https://arxiv.org/pdf/...`)
- Automatic download and processing
- Progress indication and error handling

### Language Selection

#### **Dropdown Menus** ⭐ NEW
- **Source Language**: Select from 12 common languages
- **Target Language**: Intuitive dropdown with language names
- Languages supported:
  - English, French, Spanish, German
  - Chinese, Japanese, Korean
  - Portuguese, Italian, Russian
  - Arabic, Dutch

**Benefits over text input:**
- No typing errors
- Consistent language codes
- Better UX for non-technical users

### Backend & Model Configuration

#### **Proper Separation** ⭐ NEW
- **Backend**: High-level provider (cascade_free, deepseek, openai, etc.)
- **Model**: Specific model within that backend

**Auto-Population:**
- When you select a backend, the model dropdown automatically updates
- Shows only models available for that backend
- Example: Select "anthropic" → Models: claude-3-5-sonnet, claude-3-opus, etc.

**Backend Options:**
```
cascade_free    → cascade_free
deepseek       → deepseek-chat, deepseek-reasoner
anthropic      → claude-3-5-sonnet-20241022, claude-3-opus-20240229, claude-3-sonnet-20240229
openai         → gpt-4o, gpt-4-turbo, gpt-3.5-turbo
google         → gemini-pro, gemini-1.5-flash
huggingface    → meta-llama/Llama-2-70b-chat-hf, mistralai/Mixtral-8x7B-Instruct-v0.1
ollama         → llama2, mistral, codellama
dummy          → dummy (for testing)
```

### Advanced Settings

Enhanced controls for fine-tuning translation:

| Setting | Range | Default | Description |
|---------|-------|---------|-------------|
| Translation Candidates | 1-5 | 3 | Number of candidate translations to generate |
| Context Window Size | 0-5 | 2 | Number of previous blocks to include as context |
| Temperature | 0.0-1.0 | 0.0 | Randomness in translation (0=deterministic) |
| Enable Cache | ✓/✗ | ✓ | Use cached translations for repeated text |
| Enable Reranking | ✓/✗ | ✓ | Rerank multiple candidates for best quality |
| Translate Tables | ✓/✗ | ✗ | Translate table content (preserve structure) |

### Results Display

#### **Three-Tab Result View** ⭐ NEW

**1. Translated PDF Preview**
- Visual preview of the first page
- Rendered at 2x resolution for clarity
- Download button for full PDF
- *Coming soon: Pagination controls*

**2. Quality Metrics** ⭐ NEW
- **Overall Scores:**
  - Document Quality (%)
  - Average Score
  - Health Ratio
- **Block Statistics:**
  - Total blocks processed
  - Successful translations
  - Failed translations
- **Dimension Breakdown:**
  - Individual quality dimensions
  - Per-dimension scores

**3. Translation Summary**
- File information (input/output names)
- Backend and model used
- Processing statistics
- Timing information

### Status & Logs

#### **Two-Tab Logging System** ⭐ NEW

**1. Translation Status**
- Real-time progress updates
- Step-by-step translation flow
- Success/error messages
- User-friendly language

**2. System Logs**
- Detailed technical logs
- Timestamps for all events
- Error tracking and debugging
- Persistent log history (last 100 entries)

---

## Testing Tab Features

### Comprehensive Testing ⭐ ENHANCED

#### **Run All Tests**
- One-click execution of complete test suite
- Runs pytest with verbose output
- 180-second timeout for thorough testing
- Displays exit codes and detailed results

#### **Individual Feature Tests** ⭐ NEW
Select and run specific test modules:

| Test Module | Purpose |
|-------------|---------|
| `test_adaptive_scoring.py` | Adaptive translation strategy |
| `test_backends.py` | Backend integration |
| `test_caching.py` | Translation cache functionality |
| `test_health_scoring.py` | Health scoring system |
| `test_integration.py` | End-to-end pipeline |
| `test_layout_intelligence.py` | Layout preservation |
| `test_mask_roundtrip.py` | Math masking/unmasking |
| `test_math_detection.py` | Math equation detection |
| `test_math_rendering.py` | Math-aware rendering |
| `test_reranking.py` | Candidate reranking |
| `test_table_detection.py` | Table detection |

**Benefits:**
- Test individual features in isolation
- Faster iteration during development
- Pinpoint specific issues
- Verify bug fixes

---

## Ablation Tab Improvements

### Ablation Study Types ⭐ ENHANCED

Compare configurations to measure impact:

1. **Reranking Impact**
   - Compare single candidate vs. multi-candidate with reranking
   - Measure quality improvement vs. time cost

2. **Context Window Size**
   - Test different context window sizes (0-5)
   - Analyze context contribution to quality

3. **Backend Comparison**
   - Compare different LLM backends
   - Quality, speed, and cost analysis

4. **Cache Effect**
   - Measure caching benefits
   - Speed improvement on repeated content

5. **Temperature Sensitivity**
   - Test different temperature settings
   - Balance between consistency and creativity

### Configuration Comparison ⭐ NEW

**Baseline Configuration:**
- Select backend
- Enable/disable reranking

**Test Configuration:**
- Select different backend
- Different reranking setting

### Visualizations ⭐ NEW

Automatically generated comparison plots:

- **Quality Score Bar Chart**: Visual comparison of translation quality
- **Time Comparison**: Processing time differences
- **Cost Analysis**: Cost per translation comparison

**Plot Features:**
- High-resolution (150 DPI)
- Clear labels and values
- Professional styling
- Automatic generation and display

### Detailed Information ⭐ NEW

Results include:
- Configuration summaries (JSON format)
- Quality improvement percentages
- Time overhead calculations
- Cost differences
- Actionable insights

---

## Glossary Management

### Enhanced Features ⭐ COMPLETELY NEW

#### **Search Functionality**
- Real-time search as you type
- Searches both source and target terms
- Case-insensitive matching
- Instant results

#### **Table View**
Glossary displayed as formatted markdown table:
```
| Source Term | Target Term |
|-------------|-------------|
| neural network | réseau neuronal |
| machine learning | apprentissage automatique |
```

#### **Add New Terms**
- Simple two-field form
- Source term → Target term
- Instant validation
- Automatic saving

#### **Import Glossary**
- Upload glossary files (.txt, .json)
- Supports formats:
  - `source: target` (plain text)
  - JSON key-value pairs
- Merges with existing glossary
- Preserves all terms

#### **Export Glossary**
- One-click export
- Plain text format: `source: target`
- UTF-8 encoding for all languages
- Ready for sharing or backup

#### **Download Public Glossaries** 🚧 COMING SOON
Future integration with:
- **Europarl**: EU Parliament translation corpus
- **IATE**: EU terminology database
- Custom online sources
- Domain-specific glossaries (medical, legal, etc.)

#### **Persistent Storage**
- Saved to `glossary.json`
- Automatic loading on GUI start
- UTF-8 support for all languages
- No data loss between sessions

---

## Settings & Configuration

### API Key Management ⭐ NEW

#### **In-GUI Key Configuration**
- Select backend from dropdown
- Enter API key (masked input)
- One-click save
- Automatic environment variable setup

**Supported Backends:**
- DeepSeek
- Anthropic (Claude)
- OpenAI (GPT)
- Google (Gemini)
- Hugging Face

#### **Key Storage**
- Saved to `setup_env.sh`
- Updates existing keys
- Adds new keys
- Sets environment variables immediately

#### **Security Note**
⚠️ API keys are stored in plain text in `setup_env.sh`. 
For production use, consider:
- Using environment-specific key management
- Setting keys via shell profile
- Using secrets management systems

### Backend Status Table ⭐ NEW

Real-time backend configuration status:

| Backend | Status | Models Available |
|---------|--------|------------------|
| cascade_free | ✅ Always Available | cascade_free |
| deepseek | ✅/❌ Based on API key | deepseek-chat, deepseek-reasoner |
| anthropic | ✅/❌ Based on API key | claude-3-5-sonnet, opus, sonnet |
| openai | ✅/❌ Based on API key | gpt-4o, gpt-4-turbo, gpt-3.5-turbo |
| google | ✅/❌ Based on API key | gemini-pro, gemini-1.5-flash |
| ollama | ⚙️ Requires Local Setup | llama2, mistral, codellama |
| dummy | ✅ Always Available | dummy |

**Status Indicators:**
- ✅ **Configured**: API key is set and ready
- ❌ **Not Set**: API key needs to be configured
- ⚙️ **Requires Setup**: Special setup required (e.g., Ollama local server)

#### **Refresh Button**
- Reload backend status
- Check for newly added API keys
- Verify configuration changes

### Default Settings

Set system-wide defaults:
- Default backend selection
- Default number of candidates
- *More defaults coming soon*

### Appearance

- 🌙 **Dark Mode**: Coming soon with Gradio 4.x
- 🎨 **Custom Themes**: Future enhancement
- 🖥️ **Layout Options**: Future enhancement

### System Information

Displays:
- SciTrans version
- Python version
- Gradio version
- Installation status

---

## Installation

### Quick Install

```bash
# Install with GUI support
pip install -e ".[gui]"

# Or install dependencies manually
pip install gradio requests PyMuPDF matplotlib Pillow
```

### Required Dependencies

| Package | Purpose | Required |
|---------|---------|----------|
| gradio | Web interface | ✅ Yes |
| requests | URL fetching | Optional (recommended) |
| PyMuPDF (fitz) | PDF preview | Optional (recommended) |
| matplotlib | Visualizations | Optional (recommended) |
| Pillow | Image handling | Optional (recommended) |

### Launch GUI

```bash
# Method 1: Via CLI
python3 -m scitrans.cli.main gui

# Method 2: Directly
python3 -m scitrans.gui.app

# Method 3: With options
python3 -m scitrans.gui.app --share --port 7860
```

### GUI Options

```bash
--share         # Create public shareable link (via Gradio)
--port PORT     # Set server port (default: 7860)
```

---

## Feature Comparison

| Feature | Basic GUI | Enhanced GUI |
|---------|-----------|--------------|
| PDF Upload | ✅ | ✅ |
| URL Fetching | ❌ | ✅ |
| Language Input | Text fields | Dropdowns |
| Backend/Model | Confusing | Separated & Clear |
| PDF Preview | ❌ | ✅ |
| Quality Metrics | Basic | Detailed + Interactive |
| Status Logs | Single view | Dual tabs (Status + System) |
| Testing | All tests only | Individual + All tests |
| Ablation | Basic | With visualizations |
| Glossary | Simple text | Search, import, export, table |
| API Keys | Manual setup | In-GUI management |
| Backend Status | Text | Interactive table |
| Dark Mode | ❌ | 🚧 Coming soon |

---

## Usage Tips

### Best Practices

1. **Translation:**
   - Use `cascade_free` for free, high-quality results
   - Enable caching for repeated translations
   - Use reranking for best quality (slight time increase)
   - Start with 3 candidates, adjust based on quality needs

2. **Testing:**
   - Run individual tests during development
   - Run full suite before production deployment
   - Check system logs for detailed error information

3. **Ablation Studies:**
   - Use small test documents for quick iterations
   - Compare baseline vs. enhanced configurations
   - Review visualizations for clear insights

4. **Glossary:**
   - Build glossary incrementally during translation
   - Export regularly for backup
   - Use search to verify consistency

5. **Settings:**
   - Configure all API keys at once
   - Verify backend status before translation
   - Restart GUI after changing API keys

### Troubleshooting

**GUI won't start:**
```bash
pip install gradio
```

**URL fetching fails:**
```bash
pip install requests
```

**PDF preview blank:**
```bash
pip install PyMuPDF
```

**Visualizations not showing:**
```bash
pip install matplotlib
```

**API key not working:**
- Check backend status table
- Verify key format (should start with `sk-` for most providers)
- Restart GUI after adding keys
- Check system logs for error details

---

## Keyboard Shortcuts

*Coming in future versions*

- `Ctrl+Enter`: Start translation
- `Ctrl+T`: Switch to Translation tab
- `Ctrl+G`: Focus on glossary search
- `Ctrl+L`: View system logs

---

## Future Enhancements

### Planned Features

- [ ] Pagination controls for PDF preview
- [ ] Side-by-side source/translated PDF comparison
- [ ] Real-time preview during translation
- [ ] Dark mode support
- [ ] Batch translation (multiple PDFs)
- [ ] Translation history viewer
- [ ] Export reports as PDF/HTML
- [ ] Advanced glossary: Download from Europarl, IATE
- [ ] Collaborative glossary sharing
- [ ] User accounts and preferences
- [ ] Mobile-responsive design
- [ ] Keyboard shortcuts
- [ ] Undo/redo for glossary edits
- [ ] Custom backend integration wizard

---

## Contact & Support

**Author:** Franck Davy  
**Email:** aknk.v@pm.me  
**Institution:** Wenzhou University, 2025

**Documentation:**
- `README.md` - Main documentation
- `docs/CONFIGURATION.md` - Configuration guide
- `docs/FEATURES.md` - Feature documentation
- `QUICK_START.md` - Quick start guide

**Issues:**
Report bugs or request features via the project repository.

---

## License

See LICENSE file for details.

---

*Last updated: December 30, 2025*

