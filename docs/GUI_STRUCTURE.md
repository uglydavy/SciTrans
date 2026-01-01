# SciTrans Enhanced GUI - Structure Overview

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SciTrans-LLMs Enhanced GUI                        │
│                  Adaptive Scientific PDF Translation                 │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │      Gradio Web Interface    │
                    │      (Port 7860 default)     │
                    └──────────────┬──────────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        │                          │                          │
        ▼                          ▼                          ▼
┌───────────────┐          ┌───────────────┐        ┌───────────────┐
│  Translation  │          │    Testing    │        │   Ablation    │
│      Tab      │          │      Tab      │        │      Tab      │
└───────────────┘          └───────────────┘        └───────────────┘
        │                          │                          │
        ▼                          ▼                          ▼
┌───────────────┐          ┌───────────────┐        ┌───────────────┐
│   Glossary    │          │   Settings    │        │     About     │
│      Tab      │          │      Tab      │        │      Tab      │
└───────────────┘          └───────────────┘        └───────────────┘
```

---

## Tab-by-Tab Structure

### 📄 Translation Tab

```
Translation Tab
├── Input Section
│   ├── PDF Upload (File picker)
│   └── URL Input (Text field + fetch)
│
├── Configuration Section
│   ├── Backend Selection (Dropdown)
│   ├── Model Selection (Auto-populated dropdown)
│   ├── Source Language (Dropdown: 12 languages)
│   ├── Target Language (Dropdown: 12 languages)
│   └── Advanced Settings
│       ├── Candidates (Slider: 1-5)
│       ├── Context Window (Slider: 0-5)
│       ├── Temperature (Slider: 0.0-1.0)
│       ├── Enable Cache (Checkbox)
│       ├── Enable Reranking (Checkbox)
│       └── Translate Tables (Checkbox)
│
├── Action
│   └── "Start Translation" Button
│
├── Results Section (3 Tabs)
│   ├── Tab 1: Translated PDF Preview
│   │   ├── Image Preview (first page)
│   │   └── Download Button
│   ├── Tab 2: Quality Metrics
│   │   ├── Document Quality Score
│   │   ├── Block Statistics
│   │   └── Dimension Breakdown
│   └── Tab 3: Translation Summary
│       ├── File Information
│       ├── Configuration Used
│       └── Processing Statistics
│
└── Logs Section (2 Tabs)
    ├── Tab 1: Translation Status
    │   └── User-friendly progress updates
    └── Tab 2: System Logs
        └── Technical debugging information
```

### 🧪 Testing Tab

```
Testing Tab
├── Run All Tests Section
│   ├── "Run Complete Test Suite" Button
│   └── Description of full test suite
│
├── Individual Tests Section
│   ├── Test Module Dropdown (11 options)
│   │   ├── test_adaptive_scoring.py
│   │   ├── test_backends.py
│   │   ├── test_caching.py
│   │   ├── test_health_scoring.py
│   │   ├── test_integration.py
│   │   ├── test_layout_intelligence.py
│   │   ├── test_mask_roundtrip.py
│   │   ├── test_math_detection.py
│   │   ├── test_math_rendering.py
│   │   ├── test_reranking.py
│   │   └── test_table_detection.py
│   └── "Run Selected Test" Button
│
└── Results Display
    └── Test Output (Scrollable text area)
```

### 🔬 Ablation Tab

```
Ablation Tab
├── Input Section
│   ├── PDF Upload
│   └── Study Type Dropdown
│       ├── Reranking Impact
│       ├── Context Window Size
│       ├── Backend Comparison
│       ├── Cache Effect
│       └── Temperature Sensitivity
│
├── Configuration Section
│   ├── Baseline Configuration
│   │   ├── Backend Dropdown
│   │   └── Enable Reranking Checkbox
│   └── Test Configuration
│       ├── Backend Dropdown
│       └── Enable Reranking Checkbox
│
├── Action
│   └── "Run Ablation Study" Button
│
└── Results Section
    ├── Visualization Panel
    │   └── Comparison Charts (Quality/Time/Cost)
    └── Detailed Results (Markdown)
        ├── Configuration Summaries
        ├── Quality Improvement %
        ├── Time Overhead
        └── Cost Difference
```

### 📚 Glossary Tab

```
Glossary Tab
├── Left Column
│   ├── Search Section
│   │   └── Search Input (Real-time filtering)
│   │
│   ├── Browse Section
│   │   └── Terms Table (Markdown formatted)
│   │       └── [Source Term | Target Term]
│   │
│   └── Add Term Section
│       ├── Source Term Input
│       ├── Target Term Input
│       ├── "Add Term" Button
│       └── Status Message
│
└── Right Column
    ├── Export Section
    │   ├── "Export Glossary" Button
    │   └── Download File Output
    │
    ├── Import Section
    │   ├── File Upload (.txt, .json)
    │   ├── "Import from File" Button
    │   └── Import Status
    │
    └── Public Glossaries Section (Future)
        └── "Download Europarl" Button (disabled)
```

### ⚙️ Settings Tab

```
Settings Tab
├── Left Column
│   ├── API Key Management
│   │   ├── Backend Dropdown
│   │   │   ├── deepseek
│   │   │   ├── anthropic
│   │   │   ├── openai
│   │   │   ├── google
│   │   │   └── huggingface
│   │   ├── API Key Input (Password field)
│   │   ├── "Save API Key" Button
│   │   └── Status Message
│   │
│   ├── Appearance Section
│   │   └── Dark Mode Toggle (Coming soon)
│   │
│   └── Default Settings
│       ├── Default Backend Dropdown
│       ├── Default Candidates Slider
│       └── "Save Defaults" Button (Coming soon)
│
└── Right Column
    ├── Backend Status Section
    │   ├── Status Table (Markdown)
    │   │   └── [Backend | Status | Models]
    │   └── "Refresh Status" Button
    │
    └── System Information
        ├── SciTrans Version
        ├── Python Version
        └── Gradio Version
```

### ℹ️ About Tab

```
About Tab
├── System Information
│   ├── Version & Author
│   └── Institution & Thesis Title
│
├── Research Contributions (5 novel features)
│   ├── Adaptive Translation Strategy
│   ├── Multi-Dimensional Scoring
│   ├── Repair-Driven Workflow
│   ├── Cascade-Free Backend
│   └── Integrated Scoring Pipeline
│
├── Features List
│   └── Comprehensive feature checklist
│
├── Available Backends Table
│   └── [Backend | Type | Cost | Quality]
│
├── Documentation Links
│   ├── README.md
│   ├── docs/
│   └── THESIS_RESEARCH.md
│
├── Quick Start Guide
│   └── Step-by-step instructions
│
└── Citation
    └── BibTeX format
```

---

## Component Relationships

### Translation Flow

```
┌──────────────┐
│ User Input   │
│ (PDF/URL)    │
└──────┬───────┘
       │
       ▼
┌──────────────┐     ┌──────────────┐
│ Configuration│────▶│   Backend    │
│   Settings   │     │   Selection  │
└──────┬───────┘     └──────┬───────┘
       │                    │
       ▼                    ▼
┌──────────────────────────────────┐
│     Translation Pipeline          │
│  (scitrans.pipeline.run_pipeline) │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│         Report Generation         │
│  (Scores, Health, Statistics)    │
└──────────────┬───────────────────┘
               │
       ┌───────┴───────┐
       │               │
       ▼               ▼
┌─────────────┐ ┌──────────────┐
│   Output    │ │   Quality    │
│     PDF     │ │   Metrics    │
└─────────────┘ └──────────────┘
```

### Backend Auto-Population

```
User Selects Backend
       │
       ▼
┌──────────────────────┐
│ BACKEND_MODELS Dict  │
│                      │
│ "cascade_free" →     │
│   ["cascade_free"]   │
│                      │
│ "anthropic" →        │
│   ["claude-3-5-...", │
│    "claude-3-opus",  │
│    ...]              │
└──────────┬───────────┘
           │
           ▼
    Update Model Dropdown
    with Available Models
```

### Log System

```
Translation Actions
       │
       ├──────────────────┐
       │                  │
       ▼                  ▼
┌─────────────┐    ┌──────────────┐
│ add_status()│    │  add_log()   │
│  (User-     │    │  (Technical  │
│  friendly)  │    │  details)    │
└──────┬──────┘    └──────┬───────┘
       │                  │
       ▼                  ▼
┌──────────────┐    ┌──────────────┐
│ TRANSLATION_ │    │ SYSTEM_LOGS  │
│   STATUS     │    │  (Global)    │
│  (Global)    │    │              │
└──────┬───────┘    └──────┬───────┘
       │                   │
       └───────┬───────────┘
               │
               ▼
       Display in GUI
```

---

## Data Flow

### Translation Process

```
1. User Input
   └─▶ PDF file OR URL string

2. Configuration
   ├─▶ Backend + Model selection
   ├─▶ Language pair
   └─▶ Advanced settings

3. Pre-Processing
   ├─▶ Fetch URL (if applicable)
   ├─▶ Parse PDF (PyMuPDF)
   ├─▶ Extract blocks
   └─▶ Mask math/tables

4. Translation
   ├─▶ Get backend instance
   ├─▶ Load glossary (if exists)
   ├─▶ Run pipeline
   │   ├─▶ Generate candidates
   │   ├─▶ Rerank (if enabled)
   │   ├─▶ Check cache (if enabled)
   │   └─▶ Apply context window
   └─▶ Unmask protected regions

5. Post-Processing
   ├─▶ Compute quality scores
   ├─▶ Compute health metrics
   ├─▶ Generate report
   └─▶ Render output PDF

6. Display Results
   ├─▶ PDF preview (first page)
   ├─▶ Quality metrics
   ├─▶ Download link
   └─▶ Logs
```

### Glossary Management

```
Load on Startup
      ↓
┌──────────────┐
│ glossary.json│
│  (if exists) │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  In-Memory   │◀───── Search Filter
│  Dictionary  │
└──────┬───────┘
       │
       ├────▶ Add Term ────▶ Save to JSON
       │
       ├────▶ Import File ──▶ Merge + Save
       │
       └────▶ Export ──────▶ Generate .txt
```

---

## State Management

### Global State Variables

```python
# Logging state
SYSTEM_LOGS = []          # Technical logs (last 100)
TRANSLATION_STATUS = []   # User-friendly status (last 50)

# Gradio state
glossary_state           # Current glossary dict
output_file              # Translated PDF path
output_preview           # PIL Image of first page

# Configuration
BACKEND_MODELS = {...}   # Backend → Models mapping
COMMON_LANGUAGES = [...]  # Language name → code pairs
```

### Session Persistence

```
┌──────────────────────┐
│  Backend Selection   │──▶ Retained during session
├──────────────────────┤
│  Language Preferences│──▶ Retained during session
├──────────────────────┤
│  Advanced Settings   │──▶ Retained during session
├──────────────────────┤
│  Glossary Data       │──▶ Persisted to glossary.json
├──────────────────────┤
│  API Keys            │──▶ Persisted to setup_env.sh
├──────────────────────┤
│  System Logs         │──▶ Session only (cleared on restart)
└──────────────────────┘
```

---

## File System Interactions

### Read Operations

```
┌──────────────────────┐
│  GUI Application     │
└──────────┬───────────┘
           │
           ├─▶ glossary.json (Load glossary)
           │
           ├─▶ setup_env.sh (Check API keys)
           │
           ├─▶ test_pdfs/*.pdf (Testing)
           │
           └─▶ scitrans/* (Import modules)
```

### Write Operations

```
┌──────────────────────┐
│  GUI Application     │
└──────────┬───────────┘
           │
           ├─▶ glossary.json (Save terms)
           │
           ├─▶ glossary_export.txt (Export)
           │
           ├─▶ setup_env.sh (Save API keys)
           │
           ├─▶ outputs/* (Translation results)
           │
           ├─▶ temp_downloaded.pdf (URL fetch)
           │
           └─▶ temp_ablation_plot.png (Visualizations)
```

---

## Dependencies

### Required (Core)

```
gradio
└─▶ Web interface framework
```

### Optional (Enhanced Features)

```
requests
└─▶ URL fetching

PyMuPDF (fitz)
└─▶ PDF preview rendering

matplotlib
└─▶ Ablation visualizations

Pillow (PIL)
└─▶ Image handling for previews

numpy
└─▶ Data processing for plots
```

### Install Command

```bash
pip install gradio requests PyMuPDF matplotlib Pillow numpy
# Or: pip install -e ".[gui]"
```

---

## Performance Considerations

### Optimization Strategies

1. **Lazy Loading**
   - Glossary loaded once on startup
   - Backend models populated on demand
   - PDF preview only generated when needed

2. **Caching**
   - Translation cache persists across sessions
   - Glossary cached in memory
   - Backend instances reused

3. **Async Operations**
   - Long-running tasks show progress
   - Non-blocking UI updates
   - Gradio handles concurrency

4. **Memory Management**
   - Logs capped at 100 (system) / 50 (status) entries
   - Temporary files cleaned up
   - PDF objects properly closed

---

## Security Considerations

### Current Implementation

⚠️ **Development Mode - Not Production Ready**

- API keys stored in plain text (`setup_env.sh`)
- No user authentication
- No session isolation
- File uploads not validated
- No rate limiting

### Production Recommendations

1. **Secrets Management**
   - Use environment-specific key stores
   - Encrypt sensitive data
   - Rotate keys regularly

2. **Authentication**
   - Add user login system
   - Session management
   - Role-based access control

3. **Input Validation**
   - Validate file uploads
   - Sanitize URL inputs
   - Limit file sizes

4. **Rate Limiting**
   - Limit API calls per user
   - Prevent abuse
   - Monitor usage

---

## Extensibility

### Adding New Features

#### Add New Backend

1. Create backend in `scitrans/translation/backends/`
2. Update `BACKEND_MODELS` dict in `gui/app.py`
3. Add to Settings backend status table

#### Add New Language

1. Update `COMMON_LANGUAGES` list in `gui/app.py`
2. Language code follows ISO 639-1

#### Add New Test Module

1. Create test in `tests/`
2. Add to test dropdown in Testing tab

#### Add New Ablation Type

1. Add to `ablation_type` dropdown
2. Implement logic in `run_ablation_study()`

---

## Browser Compatibility

Tested and working:
- ✅ Chrome/Chromium (Recommended)
- ✅ Firefox
- ✅ Safari
- ✅ Edge

Mobile:
- ⚠️ Limited support (responsive design coming soon)

---

## Accessibility

Current status:
- ✅ Keyboard navigation (basic)
- ✅ Screen reader friendly labels
- ⚠️ High contrast mode (pending)
- ⚠️ Font size adjustment (pending)

---

## Future Architecture Enhancements

1. **Microservices**
   - Separate translation service
   - Dedicated API server
   - Load balancing

2. **Database Integration**
   - User accounts
   - Translation history
   - Shared glossaries

3. **Real-time Updates**
   - WebSocket for live progress
   - Streaming translations
   - Collaborative editing

4. **Cloud Deployment**
   - Docker containerization
   - Kubernetes orchestration
   - CI/CD pipeline

---

**Last Updated**: December 30, 2025  
**Author**: Franck Davy, Wenzhou University

