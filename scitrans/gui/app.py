"""
SciTrans GUI - Professional web interface for scientific PDF translation.

Enhanced with all requested features:
- PDF preview with pagination
- Interactive quality scoring
- Status and system logs
- Comprehensive testing
- Ablation studies
- Enhanced glossary management
- Settings with dark/light mode
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

try:
    import gradio as gr
except ImportError as e:
    raise ImportError("Gradio not installed. Install with: pip install gradio") from e

try:
    import requests
except ImportError:
    requests = None

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

from scitrans import __version__
from scitrans.cli.main import _get_backend
from scitrans.pipeline import PipelineConfig, run_pipeline
from scitrans.utils.backend_checker import (
    validate_backend_before_use,
)
from scitrans.utils.env_loader import load_environment_variables

logger = logging.getLogger(__name__)

# Monkey-patch Gradio bug: TypeError in json_schema_to_python_type when schema is bool
# This is a bug in Gradio 4.44.1's gradio_client/utils.py line 863
# The bug: if "const" in schema where schema is a bool instead of dict
try:
    import gradio_client.utils as client_utils
    
    _original_get_type = client_utils.get_type
    
    def _patched_get_type(schema):
        """Patched version that handles bool schemas."""
        if not isinstance(schema, dict):
            # If schema is not a dict (e.g., bool), return a safe default
            return "Any"
        try:
            return _original_get_type(schema)
        except TypeError as e:
            if "not iterable" in str(e) and isinstance(schema, dict):
                # Handle case where schema dict has bool values that cause issues
                return "Any"
            raise
    
    client_utils.get_type = _patched_get_type
    
    # Also patch _json_schema_to_python_type to handle bool additionalProperties
    _original_json_schema_to_python_type = client_utils._json_schema_to_python_type
    
    def _patched_json_schema_to_python_type(schema, defs=None):
        """Patched version that handles bool additionalProperties."""
        if not isinstance(schema, dict):
            return "Any"
        # Check for problematic additionalProperties
        if "additionalProperties" in schema:
            add_props = schema["additionalProperties"]
            if isinstance(add_props, bool):
                # If additionalProperties is bool, return dict[str, Any] directly
                # instead of trying to parse it
                return "dict[str, Any]"
        try:
            return _original_json_schema_to_python_type(schema, defs)
        except Exception as e:
            # If parsing fails, return a safe default
            if "Cannot parse schema" in str(e) or "not iterable" in str(e):
                return "Any"
            raise
    
    client_utils._json_schema_to_python_type = _patched_json_schema_to_python_type
    logger.debug("Applied Gradio bug fix for json_schema_to_python_type")
except Exception as e:
    logger.warning(f"Could not apply Gradio bug fix: {e}")

# Load environment variables
try:
    loaded_vars = load_environment_variables()
    if loaded_vars:
        logger.info(f"Loaded {len(loaded_vars)} environment variables")
except Exception as e:
    logger.warning(f"Could not load environment variables: {e}")

# Language options
LANGUAGES = [
    ("English", "en"),
    ("French", "fr"),
    ("Spanish", "es"),
    ("German", "de"),
    ("Chinese", "zh"),
    ("Japanese", "ja"),
    ("Korean", "ko"),
    ("Portuguese", "pt"),
    ("Italian", "it"),
    ("Russian", "ru"),
    ("Arabic", "ar"),
    ("Dutch", "nl"),
]

# Backends with their models
BACKEND_MODELS = {
    "cascade_free": ["cascade_free"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "anthropic": [
        "claude-3-5-sonnet-20241022",
        "claude-3-opus-20240229",
        "claude-3-haiku-20240307",
    ],
    "openai": ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
    "google": ["google-translate"],
    "ollama": ["llama3.2", "llama3.1", "mistral", "gemma2"],
    "dummy": ["dummy"],
}

# System logs storage
system_logs: list[str] = []
translation_status: dict = {}

# Store PDF paths for pagination
current_source_pdf: Optional[str] = None
current_output_pdf: Optional[str] = None
source_pdf_total_pages: int = 0
output_pdf_total_pages: int = 0


def log_system(message: str, level: str = "INFO"):
    """Log system message."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [{level}] {message}"
    system_logs.append(log_entry)
    if len(system_logs) > 1000:  # Keep last 1000 logs
        system_logs.pop(0)
    # Also print to console for debugging
    if level == "ERROR":
        print(f"❌ {message}")
    elif level == "WARNING":
        print(f"⚠️ {message}")
    else:
        print(f"ℹ️ {message}")
    logger.log(getattr(logging, level, logging.INFO), message)


def pdf_to_images(pdf_path: str, page_num: int = 0) -> tuple[Optional[str], int]:
    """Convert PDF page to image for preview. Returns (image_path, total_pages)."""
    if not fitz:
        return None, 0
    try:
        import tempfile

        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        if page_num >= total_pages:
            page_num = total_pages - 1
        if page_num < 0:
            page_num = 0

        page = doc[page_num]
        pix = page.get_pixmap(matrix=2.0)  # 2x zoom for better quality
        # Use system temp directory (Gradio can access it)
        temp_dir = Path(tempfile.gettempdir())
        img_path = str(temp_dir / f"scitrans_preview_{Path(pdf_path).stem}_{page_num}.png")
        pix.save(img_path)
        doc.close()
        return img_path, total_pages
    except Exception as e:
        log_system(f"PDF preview error: {e}", "ERROR")
        return None, 0


def translate_pdf(
    pdf_file,
    pdf_url,
    backend,
    model,
    source,
    target,
    candidates,
    context,
    cache,
    rerank,
    translate_tables,
    progress=None,
):
    """Translate PDF with comprehensive status reporting."""
    if progress is None:
        progress = gr.Progress()

    global translation_status, current_source_pdf, current_output_pdf
    global source_pdf_total_pages, output_pdf_total_pages

    # Input validation
    input_path = None
    if pdf_url and pdf_url.strip():
        if not requests:
            error_msg = "Error: requests library not installed. Install with: pip install requests"
            log_system(error_msg, "ERROR")
            return None, None, None, None, None, error_msg, "", 0, 0
        try:
            log_system(f"Fetching PDF from URL: {pdf_url}")
            progress(0.05, desc="Fetching PDF from URL...")
            response = requests.get(pdf_url.strip(), timeout=30)
            response.raise_for_status()
            temp_path = Path("temp_downloaded.pdf")
            temp_path.write_bytes(response.content)
            input_path = str(temp_path)
            log_system(f"Downloaded PDF: {temp_path.name} ({len(response.content)} bytes)")
        except Exception as e:
            error_msg = f"Failed to fetch URL: {str(e)}"
            log_system(error_msg, "ERROR")
            return None, None, None, None, None, error_msg, "", 0, 0
    elif pdf_file:
        input_path = pdf_file.name
        log_system(f"Using uploaded PDF: {Path(input_path).name}")
    else:
        error_msg = "Please upload a PDF or provide a URL"
        log_system(error_msg, "ERROR")
        return None, None, None, None, None, error_msg, "", 0, 0

    # Backend validation
    progress(0.1, desc="Validating backend...")
    is_valid, error_msg = validate_backend_before_use(backend)
    if not is_valid:
        error_msg = f"Backend not available:\n{error_msg}\n\nCheck Settings tab for configuration."
        log_system(error_msg, "ERROR")
        return None, None, None, None, None, error_msg, "", 0, 0

    # Translation
    try:
        output_path = Path(input_path).with_stem(f"{Path(input_path).stem}_{target}")

        log_system(f"Starting translation: {backend}/{model}, {source} -> {target}", "INFO")
        progress(0.2, desc="Initializing backend...")

        be = _get_backend(backend, model)

        cfg = PipelineConfig(
            source_lang=source,
            target_lang=target,
            model=model,
            n_candidates=candidates,
            context_window=0,  # Disable context - user doesn't care about it
            use_cache=False,
            parallel_translation=True,  # Enable parallel translation for speed
            max_workers=4,  # Use 4 parallel workers  # ALWAYS disable cache - ensure fresh translation
            enable_reranking=rerank,  # CRITICAL: Must be True for cascade_free to work well
            translate_tables=translate_tables,
            render_mode="perfect",  # Use perfect renderer
        )

        # Warn user if using cascade_free without reranking
        if backend == "cascade_free" and not rerank:
            log_system(
                "⚠️ WARNING: Reranking is disabled. cascade_free requires reranking to select best translation. "
                "Quality may be poor. Enable reranking in Advanced Parameters.",
                "WARNING",
            )

        progress(0.3, desc="Running translation pipeline...")
        log_system("Translation pipeline started")

        report = run_pipeline(
            input_pdf=str(input_path), output_pdf=str(output_path), backend=be, cfg=cfg, progress=progress
        )

        progress(1.0, desc="Translation complete!")

        # Store status (only simple fields, not the full report object)
        translation_status = {
            "input": Path(input_path).name,
            "output": output_path.name,
            "backend": backend,
            "model": model,
            "blocks": report["num_blocks"],
            "ok_blocks": report["num_ok"],
            "failed_blocks": report["num_failed"],
            "quality": report["scoring"]["document_quality"],
            "confidence": report["scoring"]["document_confidence"],
            "acceptance_rate": report["scoring"]["acceptance_rate"],
            "time": report["elapsed_s"],
            "health": report["health"]["health_ratio"],
            # Don't store full report - it causes Gradio serialization errors
        }

        log_system(f"Translation complete: {output_path.name}")
        log_system(
            f"Quality: {report['scoring']['document_quality']:.1%}, "
            f"Blocks: {report['num_ok']}/{report['num_blocks']} OK"
        )

        # Store PDF paths for pagination
        current_source_pdf = input_path
        current_output_pdf = str(output_path)

        # Generate preview images
        source_preview, source_total = pdf_to_images(input_path, 0) if input_path else (None, 0)
        output_preview, output_total = (
            pdf_to_images(str(output_path), 0) if output_path.exists() else (None, 0)
        )

        # Store page counts
        source_pdf_total_pages = source_total
        output_pdf_total_pages = output_total

        # Format quality metrics
        quality_metrics = format_quality_metrics(report)

        # Format summary as Markdown
        summary = f"""# Translation Complete

**Input:** {Path(input_path).name}  
**Output:** {output_path.name}  
**Backend:** {backend}  
**Model:** {model}  

## Statistics
- **Blocks:** {report["num_blocks"]} total, {report["num_ok"]} OK, {report["num_failed"]} failed

## Quality Metrics
- **Quality:** {report["scoring"]["document_quality"]:.1%}
- **Confidence:** {report["scoring"]["document_confidence"]:.1%}
- **Acceptance Rate:** {report["scoring"]["acceptance_rate"]:.1%}

## Performance
- **Time:** {report["elapsed_s"]:.1f}s
- **Health:** {report["health"]["health_ratio"]:.1%}"""

        # Update status displays
        status_text = get_translation_status()
        logs_text = get_system_logs()

        return (
            str(output_path),  # output_file
            source_preview,  # source_preview
            output_preview,  # output_preview
            quality_metrics,  # quality_metrics
            summary,  # summary
            status_text,  # translation_status_display
            logs_text,  # system_logs_display
            source_total,  # source_total_pages
            output_total,  # output_total_pages
        )

    except Exception as e:
        error_msg = f"Translation failed: {str(e)}"
        log_system(error_msg, "ERROR")
        logger.error(f"Translation failed: {e}", exc_info=True)
        return None, None, None, None, None, error_msg, "", 0, 0


def format_quality_metrics(report: dict) -> str:
    """Format quality metrics for display."""
    scoring = report.get("scoring", {})
    health = report.get("health", {})

    metrics = f"""# Quality Metrics

## Overall Scores
- **Document Quality:** {scoring.get("document_quality", 0):.1%}
- **Confidence:** {scoring.get("document_confidence", 0):.1%}
- **Acceptance Rate:** {scoring.get("acceptance_rate", 0):.1%}

## Block Statistics
- **Total Blocks:** {scoring.get("blocks_total", 0)}
- **Acceptable Blocks:** {scoring.get("blocks_acceptable", 0)}
- **Need Review:** {scoring.get("blocks_need_review", 0)}
- **Need Retry:** {scoring.get("blocks_need_retry", 0)}

## Detailed Metrics
- **Placeholder Preservation:** {scoring.get("avg_placeholder_preservation", 0):.1%}
- **Numeric Accuracy:** {scoring.get("avg_numeric_accuracy", 0):.1%}
- **Format Preservation:** {scoring.get("avg_format_preservation", 0):.1%}
- **Fluency:** {scoring.get("avg_fluency", 0):.1%}
- **Fidelity:** {scoring.get("avg_fidelity", 0):.1%}

## Health Metrics
- **Health Ratio:** {health.get("health_ratio", 0):.1%}
- **OK Blocks:** {health.get("ok_blocks", 0)}
- **Warning Blocks:** {health.get("warning_blocks", 0)}
- **Failed Blocks:** {health.get("failed_blocks", 0)}

## Issues
- **Total Issues:** {scoring.get("total_issues", 0)}
- **Total Warnings:** {scoring.get("total_warnings", 0)}
"""

    return metrics


def get_models_for_backend(backend: str) -> list[str]:
    """Get available models for a backend."""
    return BACKEND_MODELS.get(backend, ["default"])


def run_all_tests():
    """Run complete test suite."""
    log_system("Running all tests...")
    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", "tests/", "-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        output = f"Exit code: {result.returncode}\n\n{result.stdout}\n\n{result.stderr}"
        log_system(f"Tests completed with exit code {result.returncode}")
        return output
    except subprocess.TimeoutExpired:
        error_msg = "Tests timed out after 5 minutes"
        log_system(error_msg, "ERROR")
        return error_msg
    except Exception as e:
        error_msg = f"Error running tests: {e}"
        log_system(error_msg, "ERROR")
        return error_msg


def run_individual_test(test_name: str):
    """Run a specific test with detailed explanation."""
    log_system(f"Running individual test: {test_name}")

    # Test descriptions
    test_descriptions = {
        "test_layout_intelligence.py": {
            "name": "PDF Parsing & Layout Intelligence",
            "description": "Tests the PDF parsing engine's ability to extract text, detect columns, headers, footers, and maintain reading order.",
            "what_it_tests": [
                "Column detection in multi-column layouts",
                "Header and footer identification",
                "Paragraph merging and text block extraction",
                "Reading order preservation",
                "Layout structure analysis",
            ],
            "useful_for": "Understanding how well the system extracts and structures content from PDFs before translation.",
        },
        "test_mask_roundtrip.py": {
            "name": "Masking & Placeholder System",
            "description": "Tests the masking engine that protects LaTeX, URLs, code, and special characters from translation.",
            "what_it_tests": [
                "LaTeX equation masking and restoration",
                "URL preservation",
                "Code block protection",
                "Placeholder roundtrip (mask → translate → restore)",
                "Special character handling",
            ],
            "useful_for": "Ensuring mathematical formulas, URLs, and code remain intact during translation.",
        },
        "test_backends.py": {
            "name": "Translation Backends",
            "description": "Tests all available translation backends (DeepSeek, Anthropic, OpenAI, Google, Ollama) for connectivity and basic functionality.",
            "what_it_tests": [
                "Backend initialization",
                "API connectivity",
                "Translation request/response handling",
                "Error handling",
                "Model availability",
            ],
            "useful_for": "Verifying that your configured backends are working correctly and can translate text.",
        },
        "test_render_basic.py": {
            "name": "PDF Rendering",
            "description": "Tests the PDF rendering engine that reconstructs translated text back into PDF format.",
            "what_it_tests": [
                "Text insertion accuracy",
                "Font size preservation",
                "Position accuracy",
                "Layout preservation",
                "Output PDF validity",
            ],
            "useful_for": "Ensuring translated content is correctly rendered back into PDF format with proper formatting.",
        },
        "test_adaptive_scoring.py": {
            "name": "Quality Scoring System",
            "description": "Tests the quality scoring system that evaluates translation quality before and after translation.",
            "what_it_tests": [
                "Pre-translation complexity scoring",
                "Post-translation quality metrics",
                "Placeholder preservation scoring",
                "Numeric accuracy detection",
                "Format preservation assessment",
                "Fluency and fidelity metrics",
            ],
            "useful_for": "Understanding how the system evaluates translation quality and identifies problematic blocks.",
        },
    }

    test_info = test_descriptions.get(
        test_name,
        {
            "name": test_name,
            "description": "Test suite for this component",
            "what_it_tests": ["Various aspects of this component"],
            "useful_for": "Verifying component functionality",
        },
    )

    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", f"tests/{test_name}", "-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Format detailed output
        output = f"""# {test_info["name"]}

## What This Test Does
{test_info["description"]}

## What It Tests
"""
        for item in test_info["what_it_tests"]:
            output += f"- {item}\n"

        output += f"""
## Why This Matters
{test_info["useful_for"]}

---

## Test Results

**Exit Code:** {result.returncode} {"✅ PASSED" if result.returncode == 0 else "❌ FAILED"}

### Standard Output:
```
{result.stdout}
```

### Error Output:
```
{result.stderr}
```
"""
        log_system(f"Test {test_name} completed with exit code {result.returncode}")
        return output
    except subprocess.TimeoutExpired:
        error_msg = f"Test {test_name} timed out after 60 seconds"
        log_system(error_msg, "ERROR")
        return f"# {test_info['name']}\n\n❌ **Test Timed Out**\n\n{error_msg}"
    except Exception as e:
        error_msg = f"Error running test {test_name}: {e}"
        log_system(error_msg, "ERROR")
        return f"# {test_info['name']}\n\n❌ **Error**\n\n{error_msg}"


def get_glossary_table(search_term: str = "") -> str:
    """Get current glossary as markdown table with search."""
    glossary_path = Path("glossary.json")
    if not glossary_path.exists():
        return "No glossary loaded"

    try:
        glossary = json.loads(glossary_path.read_text())
    except Exception:
        return "Error reading glossary"

    if not glossary:
        return "Glossary is empty"

    # Filter by search term
    if search_term:
        search_lower = search_term.lower()
        glossary = {
            k: v
            for k, v in glossary.items()
            if search_lower in k.lower() or search_lower in v.lower()
        }

    if not glossary:
        return f"No terms found matching '{search_term}'"

    table = "| Source | Target |\n|--------|--------|\n"
    for s, t in sorted(glossary.items()):
        table += f"| {s} | {t} |\n"

    return table


def add_glossary_term(source: str, target: str) -> tuple[str, str]:
    """Add term to glossary."""
    if not source or not target:
        return "Both fields required", get_glossary_table()

    glossary_path = Path("glossary.json")
    glossary = json.loads(glossary_path.read_text()) if glossary_path.exists() else {}
    glossary[source.strip()] = target.strip()
    glossary_path.write_text(json.dumps(glossary, indent=2, ensure_ascii=False))

    log_system(f"Added glossary term: {source} -> {target}")
    return f"Added: {source} -> {target}", get_glossary_table()


def get_backend_status_table() -> str:
    """Get comprehensive backend status table."""
    backends = ["deepseek", "anthropic", "openai", "google", "ollama", "cascade_free", "dummy"]

    table = "| Backend | Status | API Key | Dependencies |\n|---------|--------|---------|--------------|\n"
    for backend in backends:
        # Check API key
        if backend == "cascade_free":
            api_status = "N/A (uses free backends)"
            deps_status = "OK"
            overall_status = "✅ Available"
        elif backend == "dummy":
            api_status = "N/A"
            deps_status = "OK"
            overall_status = "✅ Available"
        else:
            key_name = f"{backend.upper()}_API_KEY"
            api_status = "✅ Set" if os.getenv(key_name) else "❌ Not Set"

            # Check dependencies
            try:
                from scitrans.utils.backend_checker import check_backend_dependencies

                deps_ok, deps_errors = check_backend_dependencies(backend)
                deps_status = "✅ OK" if deps_ok else f"❌ Missing: {', '.join(deps_errors[:2])}"
            except Exception:
                deps_status = "⚠️ Check Error"
                deps_ok = False

            if api_status == "✅ Set" and deps_ok:
                overall_status = "✅ Ready"
            elif deps_ok:
                overall_status = "⚠️ No API Key"
            else:
                overall_status = "❌ Dependencies Missing"

        table += f"| {backend} | {overall_status} | {api_status} | {deps_status} |\n"

    return table


def save_api_key(backend: str, key: str) -> str:
    """Save API key to setup_env.sh."""
    if not key:
        return "API key required"

    try:
        env_file = Path("setup_env.sh")
        content = env_file.read_text() if env_file.exists() else "#!/bin/bash\n"
        key_name = f"{backend.upper()}_API_KEY"
        key_line = f'export {key_name}="{key}"\n'

        if key_name in content:
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if line.startswith(f"export {key_name}="):
                    lines[i] = key_line.strip()
            content = "\n".join(lines)
        else:
            content += key_line

        env_file.write_text(content)
        os.environ[key_name] = key

        log_system(f"Saved API key for {backend}")
        return f"Saved {backend} API key. Restart GUI to apply."
    except Exception as e:
        error_msg = f"Error saving key: {e}"
        log_system(error_msg, "ERROR")
        return error_msg


def get_system_logs() -> str:
    """Get recent system logs."""
    return "\n".join(system_logs[-100:])  # Last 100 logs


def clear_all():
    """Clear all inputs and outputs."""
    global translation_status, current_source_pdf, current_output_pdf
    global source_pdf_total_pages, output_pdf_total_pages
    
    translation_status = {}
    current_source_pdf = None
    current_output_pdf = None
    source_pdf_total_pages = 0
    output_pdf_total_pages = 0
    
    log_system("Cleared all inputs and outputs")
    return (
        None,  # pdf_input
        "",  # pdf_url
        None,  # output_file
        None,  # source_preview
        None,  # output_preview
        "",  # quality_metrics
        "",  # summary
        "No translation performed yet",  # translation_status_display
        get_system_logs(),  # system_logs_display
        gr.update(value=0, maximum=0),  # source_page_num
        gr.update(value=0, maximum=0),  # output_page_num
        "No PDF",  # source_page_info
        "No PDF",  # output_page_info
    )


def get_translation_status() -> str:
    """Get current translation status."""
    if not translation_status:
        return "No translation performed yet"

    status = translation_status
    return f"""# Translation Status

**Input:** {status.get("input", "N/A")}
**Output:** {status.get("output", "N/A")}
**Backend:** {status.get("backend", "N/A")}
**Model:** {status.get("model", "N/A")}

## Statistics
- **Blocks:** {status.get("blocks", 0)} total
- **OK Blocks:** {status.get("ok_blocks", 0)}
- **Failed Blocks:** {status.get("failed_blocks", 0)}

## Quality
- **Quality Score:** {status.get("quality", 0):.1%}
- **Confidence:** {status.get("confidence", 0):.1%}
- **Acceptance Rate:** {status.get("acceptance_rate", 0):.1%}
- **Health Ratio:** {status.get("health", 0):.1%}

## Performance
- **Time:** {status.get("time", 0):.1f}s
"""


def create_gui():
    """Create comprehensive professional GUI."""
    
    # Custom CSS for styling
    custom_css = """
    .gradio-container {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    .main-header {
        text-align: center;
        padding: 20px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 10px;
        margin-bottom: 20px;
    }
    .centered-text {
        text-align: center;
    }
    """
    
    # Determine theme (default to Soft/Light)
    theme = gr.themes.Soft()

    with gr.Blocks(
        title="SciTrans - Scientific Document Translation",
        css=custom_css,
        theme=theme
    ) as app:
        gr.Markdown(
            """<div class="main-header"><h1>🔬 SciTrans</h1><p>Scientific Document Translation System</p></div>"""
        )

        with gr.Tabs():
            # ========== TRANSLATION TAB ==========
            with gr.Tab("Translation"):
                with gr.Row():
                    # LEFT COLUMN - Controls
                    with gr.Column(scale=1):
                        gr.Markdown("### Input")
                        with gr.Tabs():
                            with gr.Tab("Upload PDF"):
                                pdf_input = gr.File(
                                    label="Upload PDF",
                                    file_types=[".pdf"],
                                    file_count="single",
                                    height=100,
                                )
                            with gr.Tab("Fetch from URL"):
                                pdf_url = gr.Textbox(
                                    label="PDF URL",
                                    placeholder="https://example.com/document.pdf",
                                    info="Enter a URL to download PDF directly",
                                )

                        gr.Markdown("### Language Settings")
                        with gr.Row():
                            source_lang = gr.Dropdown(
                                choices=[(f"{name} ({code})", code) for name, code in LANGUAGES],
                                value="en",
                                label="Source Language",
                            )
                            target_lang = gr.Dropdown(
                                choices=[(f"{name} ({code})", code) for name, code in LANGUAGES],
                                value="fr",
                                label="Target Language",
                            )

                        gr.Markdown("### Backend & Model")
                        with gr.Row():
                            backend = gr.Dropdown(
                                choices=list(BACKEND_MODELS.keys()),
                                value="cascade_free",
                                label="Backend",
                                info="cascade_free uses ollama & google together",
                            )
                            model = gr.Dropdown(
                                choices=BACKEND_MODELS["cascade_free"],
                                value="cascade_free",
                                label="Model",
                                info="Select specific model for the backend",
                            )

                        def update_models(backend_choice):
                            models = get_models_for_backend(backend_choice)
                            return gr.Dropdown(
                                choices=models, value=models[0] if models else "default"
                            )

                        backend.change(update_models, inputs=[backend], outputs=[model])

                        with gr.Accordion("Advanced Parameters", open=False):
                            candidates = gr.Slider(
                                1,
                                5,
                                value=1,
                                step=1,
                                label="Candidates",
                                info="Number of translation candidates",
                            )
                            context = gr.Slider(
                                0,
                                10,
                                value=0,
                                step=1,
                                label="Context Window",
                                info="Previous blocks to include",
                            )
                            cache = gr.Checkbox(
                                value=True,
                                label="Use Cache",
                                info="Cache translations for faster re-runs",
                            )
                            rerank = gr.Checkbox(
                                value=True,
                                label="Enable Reranking",
                                info="Rerank multiple candidates",
                            )
                            translate_tables = gr.Checkbox(
                                value=False,
                                label="Translate Tables",
                                info="Translate table content",
                            )

                        with gr.Row():
                            translate_btn = gr.Button("🚀 Translate", variant="primary", size="lg", scale=2)
                            retranslate_btn = gr.Button("🔄 Retranslate", variant="secondary", size="lg", scale=1)
                            clear_btn = gr.Button("🗑️ Clear", variant="secondary", size="lg", scale=1)

                    # RIGHT COLUMN - Results & Preview
                    with gr.Column(scale=1):
                        with gr.Tabs():
                            # Preview Tab
                            with gr.Tab("Preview"):
                                gr.Markdown("### PDF Preview")
                                with gr.Tabs():
                                    with gr.Tab("Source PDF"):
                                        source_preview = gr.Image(
                                            label="Source PDF", type="filepath", height=600
                                        )
                                        with gr.Row():
                                            source_prev_btn = gr.Button(
                                                "◀ Previous", variant="secondary", scale=1
                                            )
                                            with gr.Column(scale=2, min_width=100):
                                                source_page_info = gr.Markdown(
                                                    "Page 1 of 1", elem_classes=["centered-text"]
                                                )
                                            source_next_btn = gr.Button(
                                                "Next ▶", variant="secondary", scale=1
                                            )
                                        source_page_num = gr.Slider(
                                            0,
                                            1,
                                            value=0,
                                            step=1,
                                            minimum=0,
                                            maximum=1,
                                            visible=False,
                                        )

                                    with gr.Tab("Translated PDF"):
                                        output_preview = gr.Image(
                                            label="Translated PDF", type="filepath", height=600
                                        )
                                        with gr.Row():
                                            output_prev_btn = gr.Button(
                                                "◀ Previous", variant="secondary", scale=1
                                            )
                                            with gr.Column(scale=2, min_width=100):
                                                output_page_info = gr.Markdown(
                                                    "Page 1 of 1", elem_classes=["centered-text"]
                                                )
                                            output_next_btn = gr.Button(
                                                "Next ▶", variant="secondary", scale=1
                                            )
                                        output_page_num = gr.Slider(
                                            0,
                                            1,
                                            value=0,
                                            step=1,
                                            minimum=0,
                                            maximum=1,
                                            visible=False,
                                        )

                                with gr.Row():
                                    download_btn = gr.Button(
                                        "📥 Download Translated PDF", variant="primary", scale=1
                                    )
                                output_file = gr.File(label="Download", visible=False)

                            # Quality Metrics Tab
                            with gr.Tab("Quality Metrics"):
                                quality_metrics = gr.Markdown(
                                    "Quality metrics will appear after translation"
                                )

                            # Status Tab
                            with gr.Tab("Status & Logs"):
                                with gr.Tabs():
                                    with gr.Tab("Translation Summary"):
                                        summary = gr.Markdown("No translation performed yet")

                                    with gr.Tab("Translation Status"):
                                        translation_status_display = gr.Markdown(
                                            "No translation performed yet"
                                        )

                                    with gr.Tab("System Logs"):
                                        system_logs_display = gr.Textbox(
                                            label="System Logs",
                                            lines=20,
                                            max_lines=50,
                                            interactive=False,
                                        )
                                        refresh_logs_btn = gr.Button("🔄 Refresh Logs")

                                refresh_logs_btn.click(
                                    get_system_logs, outputs=[system_logs_display]
                                )

            # ========== TESTING TAB ==========
            with gr.Tab("Testing"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### Test Suite")
                        test_all_btn = gr.Button("Run All Tests", variant="primary", size="lg")

                        gr.Markdown("### Individual Feature Tests")
                        test_parsing_btn = gr.Button("Test PDF Parsing", variant="secondary")
                        test_masking_btn = gr.Button("Test Masking", variant="secondary")
                        test_translation_btn = gr.Button("Test Translation", variant="secondary")
                        test_rendering_btn = gr.Button("Test Rendering", variant="secondary")
                        test_scoring_btn = gr.Button("Test Quality Scoring", variant="secondary")

                    with gr.Column(scale=2):
                        gr.Markdown("### Test Results")
                        test_output = gr.Textbox(
                            label="Test Output", lines=25, max_lines=50, interactive=False
                        )

                test_all_btn.click(run_all_tests, outputs=[test_output])
                
                def test_parsing():
                    return run_individual_test("test_layout_intelligence.py")
                def test_masking():
                    return run_individual_test("test_mask_roundtrip.py")
                def test_translation():
                    return run_individual_test("test_backends.py")
                def test_rendering():
                    return run_individual_test("test_render_basic.py")
                def test_scoring():
                    return run_individual_test("test_adaptive_scoring.py")
                
                test_parsing_btn.click(test_parsing, outputs=[test_output])
                test_masking_btn.click(test_masking, outputs=[test_output])
                test_translation_btn.click(test_translation, outputs=[test_output])
                test_rendering_btn.click(test_rendering, outputs=[test_output])
                test_scoring_btn.click(test_scoring, outputs=[test_output])

            # ========== ABLATION TAB ==========
            with gr.Tab("Ablation"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### Ablation Study Configuration")
                        ablation_backend = gr.Dropdown(
                            choices=list(BACKEND_MODELS.keys()),
                            value="cascade_free",
                            label="Backend",
                        )
                        ablation_source = gr.Dropdown(
                            choices=[(f"{name} ({code})", code) for name, code in LANGUAGES],
                            value="en",
                            label="Source Language",
                        )
                        ablation_target = gr.Dropdown(
                            choices=[(f"{name} ({code})", code) for name, code in LANGUAGES],
                            value="fr",
                            label="Target Language",
                        )

                        ablation_features = gr.CheckboxGroup(
                            choices=[
                                "Reranking",
                                "Context Window",
                                "Quality Scoring",
                                "Glossary",
                            ],
                            value=["Reranking"],
                            label="Features to Test",
                            info="Note: Masking is always enabled and cannot be disabled",
                        )

                        run_ablation_btn = gr.Button("Run Ablation Study", variant="primary")

                        with gr.Accordion("📖 How to Use Ablation Studies", open=False):
                            gr.Markdown("""
Ablation studies help you understand the impact of different features on translation quality.

1. **Select Backend & Languages**: Choose your translation backend and language pair
2. **Select Features**: Check which features to test (leave unchecked to disable)
3. **Upload PDF or Enter URL**: Provide the document to analyze
4. **Run Study**: Click "Run Ablation Study" to compare different configurations
5. **Analyze Results**: Compare quality metrics across different feature combinations

**Features:**
- **Masking**: Always enabled (protects math, URLs, code from translation)
- **Reranking**: Selects best translation from multiple candidates
- **Context Window**: Includes previous blocks for consistency
- **Quality Scoring**: Evaluates translation quality
- **Glossary**: Uses domain-specific terminology
                            """)

                    with gr.Column(scale=1):
                        gr.Markdown("### PDF Input")
                        ablation_pdf_input = gr.File(
                            label="Upload PDF for Ablation Study", file_types=[".pdf"]
                        )
                        ablation_pdf_url = gr.Textbox(
                            label="Or fetch from URL", placeholder="https://..."
                        )

                        def run_ablation_study(
                            pdf_file,
                            pdf_url,
                            backend_choice,
                            source_lang,
                            target_lang,
                            features,
                            progress=None,
                        ):
                            """Run ablation study with selected features."""
                            if progress is None:
                                progress = gr.Progress()
                            global translation_status

                            log_system(
                                f"Starting ablation study: {backend_choice}, {source_lang}->{target_lang}, features={features}"
                            )

                            # Get input PDF
                            input_path = None
                            if pdf_url and pdf_url.strip():
                                if not requests:
                                    return "Error: requests library not installed"
                                try:
                                    response = requests.get(pdf_url.strip(), timeout=30)
                                    response.raise_for_status()
                                    temp_path = Path("temp_ablation.pdf")
                                    temp_path.write_bytes(response.content)
                                    input_path = str(temp_path)
                                except Exception as e:
                                    return f"Failed to fetch URL: {str(e)}"
                            elif pdf_file:
                                input_path = pdf_file.name
                            else:
                                return "Please upload a PDF or provide a URL"

                            # Validate backend
                            is_valid, error_msg = validate_backend_before_use(backend_choice)
                            if not is_valid:
                                return f"Backend not available: {error_msg}"

                            # Feature combinations to test
                            # Note: Masking is always enabled in the pipeline (cannot be disabled)
                            # So we only test features that can actually be toggled
                            feature_combinations = []

                            # Baseline: minimal features (masking always on, but no other features)
                            feature_combinations.append(
                                {
                                    "name": "Baseline (Masking Only)",
                                    "reranking": False,
                                    "context": 0,
                                    "scoring": False,
                                    "glossary": False,
                                }
                            )

                            # All features enabled
                            feature_combinations.append(
                                {
                                    "name": "All Features",
                                    "reranking": "Reranking" in features,
                                    "context": 5 if "Context Window" in features else 0,
                                    "scoring": "Quality Scoring" in features,
                                    "glossary": "Glossary" in features,
                                }
                            )

                            # Individual features (masking is always on, so we test other features)
                            if "Reranking" in features:
                                feature_combinations.append(
                                    {
                                        "name": "Reranking Only",
                                        "reranking": True,
                                        "context": 0,
                                        "scoring": False,
                                        "glossary": False,
                                    }
                                )

                            if "Context Window" in features:
                                feature_combinations.append(
                                    {
                                        "name": "Context Window Only",
                                        "reranking": False,
                                        "context": 5,
                                        "scoring": False,
                                        "glossary": False,
                                    }
                                )

                            if "Glossary" in features:
                                feature_combinations.append(
                                    {
                                        "name": "Glossary Only",
                                        "reranking": False,
                                        "context": 0,
                                        "scoring": False,
                                        "glossary": True,
                                    }
                                )

                            results_data = []

                            try:
                                be = _get_backend(backend_choice, BACKEND_MODELS[backend_choice][0])

                                for i, combo in enumerate(feature_combinations):
                                    progress(
                                        i / len(feature_combinations),
                                        desc=f"Running: {combo['name']}...",
                                    )
                                    log_system(
                                        f"Ablation run {i + 1}/{len(feature_combinations)}: {combo['name']}"
                                    )

                                    output_path = Path(input_path).with_stem(
                                        f"{Path(input_path).stem}_ablation_{i}_{combo['name'].lower().replace(' ', '_')}"
                                    )

                                    # Load glossary if enabled
                                    glossary_dict = None
                                    if combo.get("glossary", False):
                                        try:
                                            from scitrans.translation.glossary.manager import (
                                                GlossaryManager,
                                            )

                                            gm = GlossaryManager()
                                            glossary_dict = gm.get_glossary()
                                        except Exception:
                                            glossary_dict = None

                                    cfg = PipelineConfig(
                                        source_lang=source_lang,
                                        target_lang=target_lang,
                                        model=BACKEND_MODELS[backend_choice][0],
                                        n_candidates=2 if combo["reranking"] else 1,
                                        context_window=0,  # No context - user doesn't care
                                        use_cache=False,  # Always fresh translation
                                        enable_reranking=combo["reranking"],
                                        translate_tables=False,
                                        render_mode="perfect",
                                    )

                                    # Run translation with or without glossary
                                    report = run_pipeline(
                                        input_pdf=input_path,
                                        output_pdf=str(output_path),
                                        backend=be,
                                        cfg=cfg,
                                        glossary=glossary_dict,
                                        progress=None,  # Ablation studies don't use progress
                                    )

                                    results_data.append(
                                        {
                                            "name": combo["name"],
                                            "quality": report["scoring"]["document_quality"],
                                            "confidence": report["scoring"]["document_confidence"],
                                            "acceptance_rate": report["scoring"]["acceptance_rate"],
                                            "blocks_ok": report["num_ok"],
                                            "blocks_total": report["num_blocks"],
                                            "time": report["elapsed_s"],
                                            "health": report["health"]["health_ratio"],
                                        }
                                    )

                                progress(1.0, desc="Analysis complete!")

                                # Format results
                                results = f"""# Ablation Study Results

## Configuration
- **Backend:** {backend_choice}
- **Languages:** {source_lang} → {target_lang}
- **Features Tested:** {", ".join(features) if features else "None"}
- **Total Runs:** {len(feature_combinations)}

## Results Comparison

| Configuration | Quality | Confidence | Acceptance | OK Blocks | Time (s) | Health |
|---------------|---------|------------|------------|-----------|----------|--------|
"""

                                for data in results_data:
                                    results += f"| {data['name']} | {data['quality']:.1%} | {data['confidence']:.1%} | {data['acceptance_rate']:.1%} | {data['blocks_ok']}/{data['blocks_total']} | {data['time']:.1f} | {data['health']:.1%} |\n"

                                # Find best configuration
                                best = max(results_data, key=lambda x: x["quality"])
                                results += f"\n## Best Configuration\n\n**{best['name']}** achieved the highest quality: {best['quality']:.1%}\n\n"

                                # Feature impact analysis
                                baseline = results_data[0]
                                all_features = results_data[1] if len(results_data) > 1 else None

                                if all_features:
                                    quality_improvement = (
                                        all_features["quality"] - baseline["quality"]
                                    )
                                    results += "## Feature Impact\n\n"
                                    results += f"- **Quality Improvement:** {quality_improvement:+.1%} (from {baseline['quality']:.1%} to {all_features['quality']:.1%})\n"
                                    results += f"- **Confidence Improvement:** {all_features['confidence'] - baseline['confidence']:+.1%}\n"
                                    results += f"- **Acceptance Rate Improvement:** {all_features['acceptance_rate'] - baseline['acceptance_rate']:+.1%}\n"

                                log_system(
                                    f"Ablation study complete: {len(feature_combinations)} runs"
                                )
                                return results

                            except Exception as e:
                                error_msg = f"Ablation study failed: {str(e)}"
                                log_system(error_msg, "ERROR")
                                return f"# Error\n\n{error_msg}"

                    with gr.Column(scale=2):
                        gr.Markdown("### Ablation Results")
                        ablation_results = gr.Markdown("Run an ablation study to see results here")

                        run_ablation_btn.click(
                            run_ablation_study,
                            inputs=[
                                ablation_pdf_input,
                                ablation_pdf_url,
                                ablation_backend,
                                ablation_source,
                                ablation_target,
                                ablation_features,
                            ],
                            outputs=[ablation_results],
                        )

            # ========== GLOSSARY TAB ==========
            with gr.Tab("Glossary"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### Add New Term")
                        new_source = gr.Textbox(label="Source Term", placeholder="neural network")
                        new_target = gr.Textbox(label="Target Term", placeholder="réseau neuronal")
                        add_term_btn = gr.Button("➕ Add Term", variant="primary")
                        add_status = gr.Textbox(label="Status", lines=2, interactive=False)

                        gr.Markdown("### Import/Export")
                        upload_glossary = gr.File(
                            label="Upload Glossary JSON", file_types=[".json"]
                        )
                        download_glossary_btn = gr.Button("📥 Download Current Glossary")
                        download_glossary_file = gr.File(label="Download", visible=False)

                        gr.Markdown("### Load Online Glossaries")
                        load_europarl_btn = gr.Button(
                            "📥 Load Europarl Glossary", variant="secondary"
                        )
                        load_global_btn = gr.Button("📥 Load Global Glossary", variant="secondary")

                        def download_glossary():
                            """Create downloadable glossary file."""
                            glossary_path = Path("glossary.json")
                            if not glossary_path.exists():
                                return None, "No glossary file found. Add terms first."

                            try:
                                # Return the file for download
                                log_system("Glossary download requested")
                                return str(glossary_path), "Glossary ready for download"
                            except Exception as e:
                                return None, f"Error: {e}"

                        def load_europarl_glossary():
                            """Load Europarl glossary (placeholder - would fetch from online source)."""
                            # This would fetch from Europarl or similar source
                            # For now, add some common terms
                            common_terms = {
                                "European Parliament": "Parlement européen",
                                "European Union": "Union européenne",
                                "member state": "État membre",
                                "legislation": "législation",
                                "regulation": "règlement",
                            }
                            glossary_path = Path("glossary.json")
                            existing = (
                                json.loads(glossary_path.read_text())
                                if glossary_path.exists()
                                else {}
                            )
                            existing.update(common_terms)
                            glossary_path.write_text(
                                json.dumps(existing, indent=2, ensure_ascii=False)
                            )
                            log_system(f"Loaded Europarl glossary with {len(common_terms)} terms")
                            return (
                                f"Loaded {len(common_terms)} terms from Europarl",
                                get_glossary_table(),
                            )

                        def load_global_glossary():
                            """Load global glossary (placeholder - would fetch from online source)."""
                            # This would fetch from a global glossary source
                            global_terms = {
                                "scientific": "scientifique",
                                "research": "recherche",
                                "publication": "publication",
                                "journal": "revue",
                                "conference": "conférence",
                            }
                            glossary_path = Path("glossary.json")
                            existing = (
                                json.loads(glossary_path.read_text())
                                if glossary_path.exists()
                                else {}
                            )
                            existing.update(global_terms)
                            glossary_path.write_text(
                                json.dumps(existing, indent=2, ensure_ascii=False)
                            )
                            log_system(f"Loaded global glossary with {len(global_terms)} terms")
                            return (
                                f"Loaded {len(global_terms)} terms from global glossary",
                                get_glossary_table(),
                            )

                    with gr.Column(scale=2):
                        gr.Markdown("### Glossary Terms")
                        search_term = gr.Textbox(
                            label="Search Terms",
                            placeholder="Enter term to search...",
                            info="Search filters the table below",
                        )
                        glossary_display = gr.Markdown(get_glossary_table())
                        refresh_glossary_btn = gr.Button("🔄 Refresh")

                        def upload_glossary_file(file):
                            if not file:
                                return "No file selected", get_glossary_table()
                            try:
                                glossary_path = Path("glossary.json")
                                content = Path(file.name).read_text()
                                uploaded = json.loads(content)
                                existing = (
                                    json.loads(glossary_path.read_text())
                                    if glossary_path.exists()
                                    else {}
                                )
                                existing.update(uploaded)
                                glossary_path.write_text(
                                    json.dumps(existing, indent=2, ensure_ascii=False)
                                )
                                log_system(f"Uploaded glossary with {len(uploaded)} terms")
                                return f"Uploaded {len(uploaded)} terms", get_glossary_table()
                            except Exception as e:
                                return f"Error: {e}", get_glossary_table()

                        upload_glossary.change(
                            upload_glossary_file,
                            inputs=[upload_glossary],
                            outputs=[add_status, glossary_display],
                        )

                add_term_btn.click(
                    add_glossary_term,
                    inputs=[new_source, new_target],
                    outputs=[add_status, glossary_display],
                )
                search_term.change(
                    get_glossary_table, inputs=[search_term], outputs=[glossary_display]
                )
                refresh_glossary_btn.click(
                    lambda: get_glossary_table(""), outputs=[glossary_display]
                )
                download_glossary_btn.click(
                    download_glossary, outputs=[download_glossary_file, add_status]
                )
                load_europarl_btn.click(
                    load_europarl_glossary, outputs=[add_status, glossary_display]
                )
                load_global_btn.click(load_global_glossary, outputs=[add_status, glossary_display])

            # ========== SETTINGS TAB ==========
            with gr.Tab("Settings"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### API Key Configuration")
                        backend_key = gr.Dropdown(
                            choices=["deepseek", "anthropic", "openai", "google", "ollama"],
                            label="Backend",
                            value="deepseek",
                        )
                        api_key = gr.Textbox(
                            label="API Key", type="password", placeholder="Enter API key..."
                        )
                        save_key_btn = gr.Button("💾 Save API Key", variant="primary")
                        key_status = gr.Textbox(label="Status", lines=2, interactive=False)

                        gr.Markdown("### Appearance")
                        gr.Radio(choices=["Light", "Dark", "Auto"], value="Light", label="Theme")

                        gr.Markdown("### Default Settings")
                        default_backend = gr.Dropdown(
                            choices=list(BACKEND_MODELS.keys()),
                            value="cascade_free",
                            label="Default Backend",
                        )
                        default_model_dropdown = gr.Dropdown(
                            choices=BACKEND_MODELS["cascade_free"],
                            value="cascade_free",
                            label="Default Model",
                        )

                        def update_default_model(backend_choice):
                            """Update default model dropdown based on backend."""
                            models = get_models_for_backend(backend_choice)
                            return gr.Dropdown(
                                choices=models, value=models[0] if models else "default"
                            )

                        default_backend.change(
                            update_default_model,
                            inputs=[default_backend],
                            outputs=[default_model_dropdown],
                        )

                    with gr.Column(scale=1):
                        gr.Markdown("### Backend Status")
                        backend_status = gr.Markdown(get_backend_status_table())
                        refresh_status_btn = gr.Button("🔄 Refresh Status")

                save_key_btn.click(
                    save_api_key, inputs=[backend_key, api_key], outputs=[key_status]
                )
                refresh_status_btn.click(
                    lambda: get_backend_status_table(), outputs=[backend_status]
                )

            # ========== ABOUT TAB ==========
            with gr.Tab("About"):
                gr.Markdown(f"""
# SciTrans System Information

**Version:** {__version__}
**Author:** Franck Davy
**Institution:** Wenzhou University, 2025

## Features

- **Perfect Rendering**: Exact font size preservation, bullet points, styling
- **Math-Safe Translation**: Equations and formulas protected
- **Layout Preservation**: Maintains document structure
- **Multi-Backend Support**: DeepSeek, Anthropic, OpenAI, Google, Ollama
- **Quality Scoring**: Comprehensive translation quality metrics
- **Domain Glossaries**: Specialized terminology support
- **Ablation Studies**: Feature impact analysis

## Documentation

See README.md and docs/ folder for complete documentation.

## Contact

Email: aknk.v@pm.me
                """)

        # Wire up translation
        def translate_wrapper(*args):
            result = translate_pdf(*args)
            # Update status and logs after translation
            status = get_translation_status()
            logs = get_system_logs()
            return result + (status, logs)

        def translate_with_page_update(*args):
            result = translate_wrapper(*args)
            # Extract page totals from result (indices 7 and 8)
            source_total = result[7] if len(result) > 7 else 0
            output_total = result[8] if len(result) > 8 else 0
            # Return: file, previews, metrics, summary, status, logs, sliders, info
            # Use gr.update() to update slider maximums
            return (
                result[0],  # output_file
                result[1],  # source_preview
                result[2],  # output_preview
                result[3],  # quality_metrics
                result[4],  # summary
                result[5],  # translation_status_display
                result[6],  # system_logs_display
                gr.update(maximum=max(0, source_total - 1), value=0),  # source_page_num
                gr.update(maximum=max(0, output_total - 1), value=0),  # output_page_num
                f"Page 1 of {source_total}" if source_total > 0 else "No PDF",  # source_page_info
                f"Page 1 of {output_total}" if output_total > 0 else "No PDF",  # output_page_info
            )

        translate_btn.click(
            translate_with_page_update,
            inputs=[
                pdf_input,
                pdf_url,
                backend,
                model,
                source_lang,
                target_lang,
                candidates,
                context,
                cache,
                rerank,
                translate_tables,
            ],
            outputs=[
                output_file,
                source_preview,
                output_preview,
                quality_metrics,
                summary,  # Now in Status & Logs tab
                translation_status_display,
                system_logs_display,
                source_page_num,  # Update page slider max
                output_page_num,  # Update page slider max
                source_page_info,  # Update page info
                output_page_info,  # Update page info
            ],
        )
        
        # Retranslate button - same as translate but with cache disabled
        def retranslate_wrapper(*args):
            # Replace cache input (index 8) with False
            args_list = list(args)
            args_list[8] = False  # cache = False for retranslate
            return translate_with_page_update(*args_list)
        
        retranslate_btn.click(
            retranslate_wrapper,
            inputs=[
                pdf_input,
                pdf_url,
                backend,
                model,
                source_lang,
                target_lang,
                candidates,
                context,
                cache,  # Will be overridden to False in wrapper
                rerank,
                translate_tables,
            ],
            outputs=[
                output_file,
                source_preview,
                output_preview,
                quality_metrics,
                summary,
                translation_status_display,
                system_logs_display,
                source_page_num,
                output_page_num,
                source_page_info,
                output_page_info,
            ],
        )
        
        # Clear button
        clear_btn.click(
            clear_all,
            outputs=[
                pdf_input,
                pdf_url,
                output_file,
                source_preview,
                output_preview,
                quality_metrics,
                summary,
                translation_status_display,
                system_logs_display,
                source_page_num,
                output_page_num,
                source_page_info,
                output_page_info,
            ],
        )

        # PDF pagination handlers with error handling
        def update_source_preview(page_num):
            """Update source PDF preview for different page."""
            global current_source_pdf, source_pdf_total_pages
            try:
                if not current_source_pdf:
                    return None, "No PDF loaded"
                if not Path(current_source_pdf).exists():
                    return None, "Source PDF file not found (may have been deleted)"
                page_num = int(page_num)
                if page_num < 0:
                    page_num = 0
                if page_num >= source_pdf_total_pages:
                    page_num = source_pdf_total_pages - 1
                preview, total = pdf_to_images(current_source_pdf, page_num)
                if preview is None:
                    return None, f"Failed to generate preview for page {page_num + 1}"
                return preview, f"Page {page_num + 1} of {total}"
            except Exception as e:
                log_system(f"Error updating source preview: {e}", "ERROR")
                return None, f"Error: {str(e)}"

        def update_output_preview(page_num):
            """Update output PDF preview for different page."""
            global current_output_pdf, output_pdf_total_pages
            try:
                if not current_output_pdf:
                    return None, "No PDF loaded"
                if not Path(current_output_pdf).exists():
                    return None, "Output PDF file not found (may have been deleted)"
                page_num = int(page_num)
                if page_num < 0:
                    page_num = 0
                if page_num >= output_pdf_total_pages:
                    page_num = output_pdf_total_pages - 1
                preview, total = pdf_to_images(current_output_pdf, page_num)
                if preview is None:
                    return None, f"Failed to generate preview for page {page_num + 1}"
                return preview, f"Page {page_num + 1} of {total}"
            except Exception as e:
                log_system(f"Error updating output preview: {e}", "ERROR")
                return None, f"Error: {str(e)}"

        # PDF upload handler - initialize preview
        def on_pdf_upload(pdf_file):
            """Initialize preview when PDF is uploaded."""
            global current_source_pdf, source_pdf_total_pages
            if pdf_file:
                current_source_pdf = pdf_file.name
                preview, total = pdf_to_images(pdf_file.name, 0)
                source_pdf_total_pages = total
                if preview:
                    return (
                        preview,
                        gr.update(maximum=max(0, total - 1), value=0),
                        f"Page 1 of {total}",
                    )
            return None, gr.update(maximum=0, value=0), "No PDF loaded"

        pdf_input.change(
            on_pdf_upload,
            inputs=[pdf_input],
            outputs=[source_preview, source_page_num, source_page_info],
        )

        # Pagination button handlers
        def source_prev_page(current_page):
            """Go to previous page."""
            global current_source_pdf, source_pdf_total_pages
            new_page = max(0, int(current_page) - 1)
            preview, total = (
                pdf_to_images(current_source_pdf, new_page)
                if current_source_pdf and Path(current_source_pdf).exists()
                else (None, 0)
            )
            source_pdf_total_pages = total
            return preview, gr.update(value=new_page), f"Page {new_page + 1} of {total}"

        def source_next_page(current_page):
            """Go to next page."""
            global current_source_pdf, source_pdf_total_pages
            new_page = (
                min(source_pdf_total_pages - 1, int(current_page) + 1)
                if source_pdf_total_pages > 0
                else 0
            )
            preview, total = (
                pdf_to_images(current_source_pdf, new_page)
                if current_source_pdf and Path(current_source_pdf).exists()
                else (None, 0)
            )
            source_pdf_total_pages = total
            return preview, gr.update(value=new_page), f"Page {new_page + 1} of {total}"

        def output_prev_page(current_page):
            """Go to previous page."""
            global current_output_pdf, output_pdf_total_pages
            new_page = max(0, int(current_page) - 1)
            preview, total = (
                pdf_to_images(current_output_pdf, new_page)
                if current_output_pdf and Path(current_output_pdf).exists()
                else (None, 0)
            )
            output_pdf_total_pages = total
            return preview, gr.update(value=new_page), f"Page {new_page + 1} of {total}"

        def output_next_page(current_page):
            """Go to next page."""
            global current_output_pdf, output_pdf_total_pages
            new_page = (
                min(output_pdf_total_pages - 1, int(current_page) + 1)
                if output_pdf_total_pages > 0
                else 0
            )
            preview, total = (
                pdf_to_images(current_output_pdf, new_page)
                if current_output_pdf and Path(current_output_pdf).exists()
                else (None, 0)
            )
            output_pdf_total_pages = total
            return preview, gr.update(value=new_page), f"Page {new_page + 1} of {total}"

        # Connect pagination handlers
        source_prev_btn.click(
            source_prev_page,
            inputs=[source_page_num],
            outputs=[source_preview, source_page_num, source_page_info],
        )
        source_next_btn.click(
            source_next_page,
            inputs=[source_page_num],
            outputs=[source_preview, source_page_num, source_page_info],
        )
        output_prev_btn.click(
            output_prev_page,
            inputs=[output_page_num],
            outputs=[output_preview, output_page_num, output_page_info],
        )
        output_next_btn.click(
            output_next_page,
            inputs=[output_page_num],
            outputs=[output_preview, output_page_num, output_page_info],
        )

        # Download button handler
        def download_translated_pdf():
            """Download translated PDF."""
            global current_output_pdf
            if current_output_pdf and Path(current_output_pdf).exists():
                return current_output_pdf
            return None

        download_btn.click(download_translated_pdf, outputs=[output_file])

    return app


def launch_gui(share: bool = False, server_port: int = 7860):
    """Launch the GUI."""
    logger.info("🚀 Launching SciTrans GUI...")
    app = create_gui()

    # Allow access to system temp directory for preview images
    import tempfile

    temp_dir = tempfile.gettempdir()

    # Try to launch - if localhost check fails, allow it anyway
    try:
        app.launch(
            share=share,
            server_port=server_port,
            server_name="127.0.0.1",  # Explicitly set to localhost
            show_error=True,
            show_api=False,  # Disable API info to avoid serialization bugs
            allowed_paths=[temp_dir],  # Allow access to temp directory for preview images
        )
    except ValueError as e:
        if "localhost is not accessible" in str(e):
            # If localhost check fails, try with share=True as fallback
            logger.warning("Localhost check failed, trying with share=True")
            app.launch(
                share=True,
                server_port=server_port,
                show_error=True,
                show_api=False,
                allowed_paths=[temp_dir],
            )
        else:
            raise
    logger.info(f"Open your browser to: http://localhost:{server_port}")


if __name__ == "__main__":
    launch_gui()
