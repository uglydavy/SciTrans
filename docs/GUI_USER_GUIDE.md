# SciTrans GUI User Guide

## Launching the GUI

```bash
scitrans gui
```

The GUI will open in your browser at `http://localhost:7860`

---

## Translation Tab

### Basic Translation

1. **Upload PDF or Enter URL**
   - Click "Upload PDF" and select your file, OR
   - Enter a URL in "PDF URL" field

2. **Select Languages**
   - Source Language: Dropdown (default: English)
   - Target Language: Dropdown (default: French)

3. **Choose Backend**
   - Backend: Select from dropdown (default: cascade_free)
   - Model: Auto-populated based on backend

4. **Click "Translate"**
   - Progress will be shown
   - Results appear in previews below

### Advanced Settings

Click "Advanced Parameters" to expand:

- **Candidates**: Number of translation candidates (1-10, default: 3)
- **Context Window**: Previous blocks for context (0-10, default: 2)
- **Cache**: Enable/disable translation caching
- **Reranking**: Enable/disable candidate reranking
- **Translate Tables**: Whether to translate tables

### Results

After translation:

- **Source PDF Preview**: Left side, with pagination
- **Translated PDF Preview**: Right side, with pagination
- **Quality Metrics**: Detailed scoring breakdown
- **Summary**: Translation statistics
- **Download Button**: Download translated PDF

### PDF Preview

- Use sliders to navigate pages
- Page info shows "Page X of Y"
- Previews update automatically

---

## Testing Tab

### Run All Tests

Click "Run All Tests" to test:
- PDF parsing
- Masking engine
- Translation backends
- Rendering
- Quality scoring

### Individual Tests

Test specific components:
- **Test Parsing**: PDF structure extraction
- **Test Masking**: Math/URL/code protection
- **Test Translation**: Backend connectivity
- **Test Rendering**: PDF reconstruction
- **Test Scoring**: Quality metrics

Results appear in the "Test Output" textbox.

---

## Ablation Tab

### Run Ablation Study

1. **Upload PDF** (or enter URL)
2. **Select Backend** and **Languages**
3. **Choose Features** to test:
   - Reranking
   - Context Window
   - Quality Scoring
   - Glossary
4. **Click "Run Ablation Study"**

### Results

The study compares:
- Baseline (masking only)
- All features enabled
- Individual features

Results show:
- Quality scores
- Confidence levels
- Acceptance rates
- Processing time
- Health metrics

---

## Glossary Tab

### Add Terms

1. Enter **Source Term** (e.g., "neural network")
2. Enter **Target Term** (e.g., "réseau neuronal")
3. Click "Add Term"

### Search Glossary

1. Enter search term
2. Click "Search"
3. Matching terms appear in table

### Import/Export

- **Upload**: Upload JSON glossary file
- **Download**: Download current glossary

### Glossary Table

Shows all cached terms with:
- Source term
- Target term
- Date added

---

## Settings Tab

### API Key Configuration

1. Select **Backend** (deepseek, anthropic, openai, etc.)
2. Enter **API Key**
3. Click "Save API Key"
4. Key is saved to `setup_env.sh`

### Backend Status

Shows table of all backends:
- ✅ Available (green)
- ❌ Missing dependencies (red)
- ⚠️ Need API key (yellow)
- ❌ Error (red)

Click "Refresh Status" to update.

### Appearance

- **Theme**: Light/Dark/Auto (requires restart)

### Default Settings

- **Default Backend**: Set preferred backend
- **Default Model**: Set preferred model

---

## Tips & Tricks

### Fast Translation

- Use `cascade_free` backend
- Set candidates to 1
- Disable reranking
- Disable cache (if testing)

### High Quality

- Use `anthropic` or `openai` backend
- Set candidates to 5
- Enable reranking
- Enable context window (3-5)
- Use perfect render mode

### Debugging

- Enable verbose logging
- Check "System Logs" tab
- Review artifacts in `outputs/` directory
- Check `report.json` for details

---

## Keyboard Shortcuts

- **Ctrl+C**: Stop translation (in terminal)
- **F5**: Refresh page (in browser)

---

## Common Issues

### "Translation not starting"

- Check backend status in Settings tab
- Verify API keys are set
- Check system logs for errors

### "Preview not showing"

- Wait for translation to complete
- Check if PDF was created
- Try refreshing the page

### "Quality scores low"

- Try different backend
- Increase number of candidates
- Enable reranking
- Check source PDF quality

---

## Getting Help

- Check "System Logs" for error messages
- Review "Translation Status" for details
- See CLI reference: `scitrans --help`
- Check artifacts in `outputs/` directory

