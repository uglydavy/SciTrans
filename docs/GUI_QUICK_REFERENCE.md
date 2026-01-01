# SciTrans Enhanced GUI - Quick Reference

## 🚀 Quick Start

### Launch GUI
```bash
python3 -m scitrans.cli.main gui
# Or: python3 -m scitrans.gui.app
```

### First Time Setup
1. Go to **⚙️ Settings** tab
2. Add API keys for desired backends
3. Restart GUI

---

## 📄 Translation Tab

### Input Options
- **Upload PDF**: Drag & drop or browse
- **Fetch from URL**: Paste URL like `https://arxiv.org/pdf/...`

### Configuration
| Setting | Recommended | Purpose |
|---------|-------------|---------|
| Backend | `cascade_free` | Free, high-quality ensemble |
| Model | Auto-selected | Based on backend |
| Source Language | Select from dropdown | Source document language |
| Target Language | Select from dropdown | Desired output language |
| Candidates | `3` | Balance quality vs. speed |
| Context Window | `2` | Good context awareness |
| Temperature | `0.0` | Deterministic translations |
| Enable Cache | ✓ | Speed up repeated content |
| Enable Reranking | ✓ | Best quality selection |
| Translate Tables | ✗ | Preserve table structure |

### Results View
- **Tab 1**: Translated PDF preview + download
- **Tab 2**: Quality metrics breakdown
- **Tab 3**: Translation summary

### Logs View
- **Tab 1**: Translation status (user-friendly)
- **Tab 2**: System logs (technical details)

---

## 🧪 Testing Tab

### Run All Tests
Click **"Run Complete Test Suite"** → Wait 2-3 minutes → Review results

### Run Individual Test
1. Select test module from dropdown
2. Click **"Run Selected Test"**
3. Review specific feature results

### Available Tests
- `test_backends.py` - Backend integration
- `test_caching.py` - Cache functionality
- `test_health_scoring.py` - Quality scoring
- `test_integration.py` - Full pipeline
- `test_math_rendering.py` - Math handling
- `test_reranking.py` - Candidate selection
- More...

---

## 🔬 Ablation Tab

### Quick Ablation Study
1. Upload test PDF
2. Select study type (e.g., "Backend Comparison")
3. Configure baseline (e.g., `dummy` backend)
4. Configure test (e.g., `cascade_free` backend)
5. Click **"Run Ablation Study"**
6. Review visualization + detailed results

### Study Types
- **Reranking Impact**: Multi-candidate vs. single
- **Context Window Size**: Context effect on quality
- **Backend Comparison**: Compare LLM providers
- **Cache Effect**: Caching performance
- **Temperature Sensitivity**: Temperature impact

---

## 📚 Glossary Tab

### Search Terms
Type in search box → Results filter in real-time

### Add Term
1. Enter source term (e.g., "neural network")
2. Enter target term (e.g., "réseau neuronal")
3. Click **"Add Term"**

### Import Glossary
1. Prepare file with format: `source: target` (one per line)
2. Click file upload
3. Click **"Import from File"**

### Export Glossary
Click **"Export Glossary"** → Download `.txt` file

### Future Features
- Download from Europarl corpus
- Download from IATE terminology database

---

## ⚙️ Settings Tab

### Add API Key
1. Select backend (e.g., "deepseek")
2. Enter API key (will be masked)
3. Click **"Save API Key"**
4. Restart GUI

### Check Backend Status
- View table showing all backends
- ✅ = Configured and ready
- ❌ = API key needed
- ⚙️ = Special setup required

### Refresh Status
Click **"Refresh Status"** after adding keys

---

## 💡 Pro Tips

### Best Quality
```
Backend: anthropic
Model: claude-3-5-sonnet-20241022
Candidates: 5
Reranking: ✓
Context Window: 3
```

### Best Speed (Free)
```
Backend: cascade_free
Model: cascade_free
Candidates: 1
Reranking: ✗
Context Window: 0
Cache: ✓
```

### Balanced (Recommended)
```
Backend: cascade_free
Model: cascade_free
Candidates: 3
Reranking: ✓
Context Window: 2
Cache: ✓
```

---

## 🔧 Troubleshooting

| Problem | Solution |
|---------|----------|
| GUI won't start | `pip install gradio` |
| Can't fetch URLs | `pip install requests` |
| No PDF preview | `pip install PyMuPDF` |
| No visualizations | `pip install matplotlib` |
| API key rejected | Check format, restart GUI |
| Translation failed | Check System Logs tab |

---

## 📊 Backend Comparison

| Backend | Cost | Speed | Quality | Setup |
|---------|------|-------|---------|-------|
| cascade_free | Free | Fast | ⭐⭐⭐⭐⭐ | None |
| deepseek | Free tier | Fast | ⭐⭐⭐⭐⭐ | API key |
| anthropic | $$ | Medium | ⭐⭐⭐⭐⭐ | API key |
| openai | $$$ | Medium | ⭐⭐⭐⭐ | API key |
| google | Free | Fast | ⭐⭐⭐ | API key |
| ollama | Free | Slow | ⭐⭐⭐ | Local server |
| dummy | Free | Instant | ⭐ | None (testing) |

---

## 🌍 Supported Languages

Common languages available in dropdowns:
- 🇬🇧 English (`en`)
- 🇫🇷 French (`fr`)
- 🇪🇸 Spanish (`es`)
- 🇩🇪 German (`de`)
- 🇨🇳 Chinese (`zh`)
- 🇯🇵 Japanese (`ja`)
- 🇰🇷 Korean (`ko`)
- 🇵🇹 Portuguese (`pt`)
- 🇮🇹 Italian (`it`)
- 🇷🇺 Russian (`ru`)
- 🇸🇦 Arabic (`ar`)
- 🇳🇱 Dutch (`nl`)

---

## 🎯 Common Workflows

### Workflow 1: Quick Translation
1. Upload PDF
2. Select target language
3. Click "Start Translation"
4. Download result

### Workflow 2: High-Quality Translation
1. Go to Settings → Add Anthropic API key → Restart
2. Upload PDF
3. Backend: `anthropic`, Model: `claude-3-5-sonnet-20241022`
4. Candidates: `5`, Reranking: ✓
5. Click "Start Translation"
6. Review quality metrics
7. Download result

### Workflow 3: Batch Testing
1. Go to Testing tab
2. Click "Run Complete Test Suite"
3. Verify all features work
4. Check for any failures in output

### Workflow 4: Compare Backends
1. Go to Ablation tab
2. Upload test PDF
3. Select "Backend Comparison"
4. Baseline: `dummy`, Test: `cascade_free`
5. Run ablation
6. Review visualization

### Workflow 5: Build Domain Glossary
1. Translate first document
2. Note domain-specific terms
3. Go to Glossary tab
4. Add terms one by one
5. Export glossary
6. Share with team or reuse for next document

---

## 📱 Access from Other Devices

### Local Network
```bash
python3 -m scitrans.gui.app --share
```
Look for: "Running on public URL: https://xxxxx.gradio.live"

### Custom Port
```bash
python3 -m scitrans.gui.app --port 8080
```

---

## 🆘 Getting Help

1. **Check Documentation**
   - `docs/GUI_ENHANCED_FEATURES.md` - Full feature guide
   - `docs/CONFIGURATION.md` - Configuration details
   - `QUICK_START.md` - Getting started

2. **Check Logs**
   - Translation tab → System Logs tab
   - Look for ERROR messages
   - Copy error details for support

3. **Test Individual Features**
   - Testing tab → Select specific test
   - Identify which feature has issues

4. **Contact Support**
   - Email: aknk.v@pm.me
   - Include: error message, system info, steps to reproduce

---

## ⌨️ Keyboard Shortcuts (Coming Soon)

- `Ctrl+Enter` - Start translation
- `Ctrl+T` - Switch to Translation tab
- `Ctrl+S` - Open Settings
- `Ctrl+G` - Focus glossary search
- `Ctrl+L` - View system logs

---

## 📚 Learn More

- **Full Documentation**: `docs/GUI_ENHANCED_FEATURES.md`
- **Research Paper**: `THESIS_RESEARCH.md`
- **API Reference**: `docs/API_KEYS_SETUP.md`
- **Configuration Guide**: `docs/CONFIGURATION.md`

---

## 🎓 Citation

```bibtex
@mastersthesis{davy2025scitrans,
  title={Adaptive Document Translation Enhanced by Technology based on LLMs},
  author={Davy, Franck},
  year={2025},
  school={Wenzhou University}
}
```

---

**Version**: 1.0  
**Last Updated**: December 30, 2025  
**Author**: Franck Davy, Wenzhou University

