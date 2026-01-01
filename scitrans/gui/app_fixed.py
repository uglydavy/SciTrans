"""
SciTrans GUI - Clean, functional web interface for scientific PDF translation.

Provides interface for:
- Translation with proper layout
- Testing and validation
- Ablation studies
- Glossary management
- Settings
- System information
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

try:
    import gradio as gr  # type: ignore
except ImportError as e:
    raise ImportError(
        "Gradio not installed. Install with: pip install -e '.[gui]' or pip install gradio"
    ) from e

try:
    import requests
except ImportError:
    requests = None  # type: ignore

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None  # type: ignore

from scitrans import __version__
from scitrans.cli.main import _get_backend
from scitrans.pipeline import PipelineConfig, run_pipeline

logger = logging.getLogger(__name__)

# Common languages
COMMON_LANGUAGES = [
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

# Backend to model mappings
BACKEND_MODELS = {
    "cascade_free": ["cascade_free"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "anthropic": [
        "claude-3-5-sonnet-20241022",
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229",
    ],
    "openai": ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
    "google": ["gemini-pro", "gemini-1.5-flash"],
    "huggingface": ["meta-llama/Llama-2-70b-chat-hf", "mistralai/Mixtral-8x7B-Instruct-v0.1"],
    "ollama": ["llama2", "mistral", "codellama"],
    "dummy": ["dummy"],
}


def get_models_for_backend(backend: str) -> list[str]:
    """Get available models for a backend."""
    return BACKEND_MODELS.get(backend, [backend])


def fetch_pdf_from_url(url: str) -> tuple[str | None, str]:
    """Fetch a PDF from a URL."""
    if not requests:
        return None, "❌ requests library not installed. Install with: pip install requests"

    try:
        logger.info(f"Fetching PDF from URL: {url}")
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        # Save to temporary file
        temp_path = Path("temp_downloaded.pdf")
        temp_path.write_bytes(response.content)

        logger.info(f"✅ Successfully downloaded PDF ({len(response.content)} bytes)")
        return str(temp_path), f"✅ Downloaded PDF from {url}"
    except Exception as e:
        logger.error(f"Failed to fetch PDF: {e}")
        return None, f"❌ Error: {str(e)}"


def translate_pdf(
    pdf_file,
    pdf_url: str,
    backend: str,
    model: str,
    source: str,
    target: str,
    n_candidates: int,
    context_window: int,
    temperature: float,
    use_cache: bool,
    enable_reranking: bool,
    translate_tables: bool,
):
    """Translate a PDF file."""
    # Determine input source
    input_path = None
    status_msg = "🚀 Starting translation...\n"

    if pdf_url and pdf_url.strip():
        status_msg += f"📥 Fetching PDF from URL: {pdf_url}\n"
        input_path, msg = fetch_pdf_from_url(pdf_url.strip())
        status_msg += msg + "\n"
        if not input_path:
            return None, f"❌ Failed to fetch PDF: {pdf_url}", status_msg
    elif pdf_file is not None:
        input_path = Path(pdf_file.name)
        status_msg += f"📄 Using uploaded PDF: {input_path.name}\n"
    else:
        return None, "❌ Please upload a PDF file or provide a URL.", status_msg

    try:
        output_path = Path(input_path).with_stem(f"{Path(input_path).stem}_{target}")

        status_msg += f"🔧 Configuring backend: {backend} ({model})\n"
        be = _get_backend(backend, model)

        status_msg += f"⚙️ Pipeline config: {n_candidates} candidates, context={context_window}\n"
        cfg = PipelineConfig(
            source_lang=source,
            target_lang=target,
            model=model,
            temperature=temperature,
            n_candidates=n_candidates,
            context_window=context_window,
            use_cache=use_cache,
            enable_reranking=enable_reranking,
            translate_tables=translate_tables,
        )

        status_msg += "🔄 Running translation pipeline...\n"
        report = run_pipeline(
            input_pdf=str(input_path), output_pdf=str(output_path), backend=be, cfg=cfg
        )

        # Format summary
        summary = f"""✅ Translation Complete!

**Input:** {Path(input_path).name}
**Output:** {output_path.name}
**Backend:** {backend} ({model})
**Blocks:** {report["num_blocks"]} total, {report["num_ok"]} OK, {report["num_failed"]} failed
**Quality:** {report["scoring"]["document_quality"]:.1%}
**Time:** {report["elapsed_s"]:.2f}s
**Health:** {report["health"]["health_ratio"]:.1%} blocks healthy
"""

        status_msg += "✅ Translation completed successfully!\n"
        logger.info(f"Translation complete: {input_path} -> {output_path}")

        return str(output_path), summary, status_msg

    except Exception as e:
        error_msg = f"❌ Translation Error: {str(e)}"
        status_msg += error_msg + "\n"
        logger.error(f"Translation error: {e}", exc_info=True)
        return None, error_msg, status_msg


def run_all_tests():
    """Run the full test suite."""
    logger.info("Running full test suite...")
    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", "tests/", "-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=180,
        )
        output = f"Exit code: {result.returncode}\n\n{result.stdout}\n\n{result.stderr}"
        logger.info(f"Tests completed with exit code {result.returncode}")
        return output
    except Exception as e:
        error = f"❌ Error running tests: {e}"
        logger.error(error)
        return error


def run_individual_test(test_name: str):
    """Run an individual test file."""
    logger.info(f"Running test: {test_name}")
    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", f"tests/{test_name}", "-v"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = f"Exit code: {result.returncode}\n\n{result.stdout}"
        logger.info(f"Test {test_name} completed with exit code {result.returncode}")
        return output
    except Exception as e:
        error = f"❌ Error: {e}"
        logger.error(error)
        return error


def load_glossary() -> dict:
    """Load glossary from file."""
    glossary_path = Path("glossary.json")
    if not glossary_path.exists():
        return {}
    try:
        return json.loads(glossary_path.read_text())
    except Exception:
        return {}


def save_glossary(source: str, target: str) -> str:
    """Add a term to the glossary."""
    if not source or not target:
        return "❌ Both source and target terms are required."

    glossary = load_glossary()
    glossary[source.strip()] = target.strip()

    try:
        glossary_path = Path("glossary.json")
        glossary_path.write_text(json.dumps(glossary, indent=2, ensure_ascii=False))
        logger.info(f"Added glossary term: {source} -> {target}")
        return f"✅ Added term to glossary ({len(glossary)} terms total)"
    except Exception as e:
        return f"❌ Error: {e}"


def get_glossary_table() -> str:
    """Get glossary as markdown table."""
    glossary = load_glossary()
    if not glossary:
        return "No terms in glossary."

    table = "| Source Term | Target Term |\n|-------------|-------------|\n"
    for source, target in sorted(glossary.items()):
        table += f"| {source} | {target} |\n"

    return table


def save_api_key(backend: str, api_key: str) -> str:
    """Save API key to environment file."""
    if not api_key:
        return "❌ API key cannot be empty."

    env_file = Path("setup_env.sh")

    # Read existing content
    if env_file.exists():
        content = env_file.read_text()
    else:
        content = "#!/bin/bash\n# API Keys for SciTrans\n\n"

    # Update or add the key
    key_name = f"{backend.upper()}_API_KEY"
    key_line = f'export {key_name}="{api_key}"\n'

    if key_name in content:
        # Replace existing
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if line.startswith(f"export {key_name}="):
                lines[i] = key_line.strip()
        content = "\n".join(lines)
    else:
        # Add new
        content += key_line

    env_file.write_text(content)

    # Also set in current environment
    os.environ[key_name] = api_key

    logger.info(f"Saved API key for {backend}")
    return f"✅ API key saved for {backend}. Restart the GUI to apply changes."


def get_backend_status() -> str:
    """Get status of all backends."""
    backends = ["deepseek", "anthropic", "openai", "google", "huggingface"]

    table = "| Backend | Status | Models Available |\n|---------|--------|------------------|\n"

    for backend in backends:
        key_name = f"{backend.upper()}_API_KEY"
        status = "✅ Configured" if os.getenv(key_name) else "❌ Not Set"
        models = ", ".join(BACKEND_MODELS.get(backend, [])[:3])
        table += f"| {backend} | {status} | {models} |\n"

    # Add free backends
    table += "| cascade_free | ✅ Always Available | cascade_free |\n"
    table += "| dummy | ✅ Always Available | dummy |\n"
    table += "| ollama | ⚙️ Requires Local Setup | llama2, mistral |\n"

    return table


def create_gui():
    """Create and launch the GUI with clean layout."""

    # Custom CSS for better styling
    custom_css = """
    .gradio-container {
        font-family: 'Inter', sans-serif;
        max-width: 1400px !important;
    }
    .gr-button-primary {
        background: linear-gradient(90deg, #4b6cb7 0%, #182848 100%);
    }
    """

    with gr.Blocks(title="SciTrans LLMs", css=custom_css, theme=gr.themes.Soft()) as app:
        gr.Markdown("""
        # 🌍 SciTrans LLMs
        ## Scientific Document Translation • v1.0
        """)

        with gr.Tabs():
            # ===== TAB 1: TRANSLATION =====
            with gr.Tab("Translation"):
                with gr.Row():
                    # LEFT COLUMN - Controls
                    with gr.Column(scale=1):
                        # Upload section
                        with gr.Group():
                            gr.Markdown("### Upload PDF")
                            pdf_input = gr.File(label="Upload PDF", file_types=[".pdf"])
                            gr.Markdown("**OR**")
                            pdf_url_input = gr.Textbox(
                                label="From URL", placeholder="https://example.com/paper.pdf"
                            )

                        # Language selection
                        with gr.Row():
                            source_lang = gr.Dropdown(
                                choices=[(name, code) for name, code in COMMON_LANGUAGES],
                                value="en",
                                label="From",
                            )
                            target_lang = gr.Dropdown(
                                choices=[(name, code) for name, code in COMMON_LANGUAGES],
                                value="fr",
                                label="To",
                            )

                        # Backend selection
                        backend_dropdown = gr.Dropdown(
                            choices=list(BACKEND_MODELS.keys()),
                            value="cascade_free",
                            label="Backend",
                        )

                        model_dropdown = gr.Dropdown(
                            choices=BACKEND_MODELS["cascade_free"],
                            value="cascade_free",
                            label="Model (for Ollama/HuggingFace/OpenAI/etc.)",
                        )

                        # Advanced Features (checkboxes)
                        gr.Markdown("### Advanced Features")
                        gr.Checkbox(value=True, label="Masking", info="Protect LaTeX, URLs, code")
                        reranking = gr.Checkbox(
                            value=True, label="Reranking", info="Select best translation"
                        )
                        gr.Checkbox(value=True, label="Context", info="Use document context")
                        gr.Checkbox(value=True, label="Glossary", info="Use domain terms")

                        # Advanced Parameters (collapsible)
                        with gr.Accordion("Advanced Parameters", open=False):
                            n_candidates = gr.Slider(
                                1, 4, value=2, step=1, label="Number of candidates (turns)"
                            )
                            context_window = gr.Slider(
                                0, 10, value=5, step=1, label="Context window (blocks)"
                            )
                            temperature = gr.Slider(
                                0, 1, value=0.7, step=0.1, label="Quality threshold"
                            )
                            use_cache = gr.Checkbox(value=True, label="Enable Cache")
                            translate_tables = gr.Checkbox(value=False, label="Translate Tables")

                        # Action buttons
                        translate_btn = gr.Button("🚀 Translate", variant="primary", size="lg")
                        gr.Button("🗑️ Clear", variant="secondary")

                    # RIGHT COLUMN - Results
                    with gr.Column(scale=1):
                        # Results tabs
                        with gr.Tabs():
                            with gr.Tab("Source"):
                                gr.Markdown("*Upload a PDF to see preview*")

                            with gr.Tab("Translated"):
                                output_file = gr.File(label="Download Translated PDF")
                                translation_summary = gr.Textbox(label="Summary", lines=10)

                            with gr.Tab("Text Preview"):
                                gr.Markdown("*Text preview coming soon*")

                            with gr.Tab("Quality Scores"):
                                gr.Markdown("*Quality scores will appear after translation*")

                        # Status box
                        status_output = gr.Textbox(label="Status", lines=15, max_lines=20)

                # Wire up handlers
                def update_models(backend):
                    models = get_models_for_backend(backend)
                    return gr.Dropdown(choices=models, value=models[0])

                backend_dropdown.change(
                    update_models, inputs=[backend_dropdown], outputs=[model_dropdown]
                )

                translate_btn.click(
                    translate_pdf,
                    inputs=[
                        pdf_input,
                        pdf_url_input,
                        backend_dropdown,
                        model_dropdown,
                        source_lang,
                        target_lang,
                        n_candidates,
                        context_window,
                        temperature,
                        use_cache,
                        reranking,
                        translate_tables,
                    ],
                    outputs=[output_file, translation_summary, status_output],
                )

            # ===== TAB 2: TESTING =====
            with gr.Tab("Testing"):
                gr.Markdown("### System Tests")

                with gr.Row():
                    # Left column - Test controls
                    with gr.Column():
                        gr.Markdown("#### Backend Test")
                        gr.Dropdown(
                            choices=list(BACKEND_MODELS.keys()), value="deepseek", label="Backend"
                        )
                        gr.Button("▶ Test Backend", variant="primary")
                        gr.Textbox(label="Result", lines=10)

                        gr.Markdown("#### Individual Tests")
                        test_dropdown = gr.Dropdown(
                            choices=[
                                "test_adaptive_scoring.py",
                                "test_backends.py",
                                "test_caching.py",
                                "test_health_scoring.py",
                                "test_integration.py",
                                "test_layout_intelligence.py",
                                "test_mask_roundtrip.py",
                                "test_math_detection.py",
                                "test_math_rendering.py",
                                "test_reranking.py",
                                "test_table_detection.py",
                            ],
                            label="Select Test Module",
                        )
                        test_individual_btn = gr.Button("Run Selected Test")

                    # Right column - Test results
                    with gr.Column():
                        gr.Markdown("#### All Tests")
                        test_all_btn = gr.Button("🚀 Run Complete Test Suite", variant="primary")
                        test_output = gr.Textbox(label="Test Results", lines=25)

                test_all_btn.click(run_all_tests, inputs=[], outputs=[test_output])
                test_individual_btn.click(
                    run_individual_test, inputs=[test_dropdown], outputs=[test_output]
                )

            # ===== TAB 3: SETTINGS =====
            with gr.Tab("Settings"):
                with gr.Row():
                    # Left column - API Keys
                    with gr.Column():
                        gr.Markdown("### 🔑 API Keys Management")

                        backend_for_key = gr.Dropdown(
                            choices=["deepseek", "anthropic", "openai", "google", "huggingface"],
                            label="Backend",
                        )
                        api_key_input = gr.Textbox(
                            label="API Key", placeholder="sk-...", type="password"
                        )
                        save_key_btn = gr.Button("💾 Save Key", variant="primary")
                        key_status = gr.Textbox(label="Status", lines=2)

                        gr.Markdown("""
                        **Note:** API keys are saved to `setup_env.sh`.  
                        Restart the GUI after updating keys.
                        """)

                    # Right column - Status & Settings
                    with gr.Column():
                        gr.Markdown("### Translation Settings")
                        gr.Markdown(
                            "DeepSeek recommended for best quality/price. Free options have rate limits."
                        )

                        gr.Dropdown(
                            choices=list(BACKEND_MODELS.keys()),
                            value="deepseek",
                            label="Default Backend",
                        )

                        gr.Markdown("### Backend Status")
                        backend_status_table = gr.Markdown(get_backend_status())
                        refresh_status_btn = gr.Button("🔄 Refresh Status")

                save_key_btn.click(
                    save_api_key, inputs=[backend_for_key, api_key_input], outputs=[key_status]
                )

                refresh_status_btn.click(
                    get_backend_status, inputs=[], outputs=[backend_status_table]
                )

            # ===== TAB 4: GLOSSARY =====
            with gr.Tab("Glossary"):
                gr.Markdown("### Domain Terminology Management")

                with gr.Row():
                    # Left column - Add terms
                    with gr.Column():
                        gr.Markdown("#### Add New Term")
                        new_source = gr.Textbox(label="Source Term", placeholder="neural network")
                        new_target = gr.Textbox(label="Target Term", placeholder="réseau neuronal")
                        add_term_btn = gr.Button("Add Term", variant="primary")
                        glossary_status = gr.Textbox(label="Status", lines=2)

                    # Right column - View terms
                    with gr.Column():
                        gr.Markdown("#### Current Glossary")
                        glossary_display = gr.Markdown(get_glossary_table())
                        refresh_glossary_btn = gr.Button("🔄 Refresh")

                def add_and_refresh(source, target):
                    status = save_glossary(source, target)
                    table = get_glossary_table()
                    return status, table, "", ""

                add_term_btn.click(
                    add_and_refresh,
                    inputs=[new_source, new_target],
                    outputs=[glossary_status, glossary_display, new_source, new_target],
                )

                refresh_glossary_btn.click(
                    get_glossary_table, inputs=[], outputs=[glossary_display]
                )

            # ===== TAB 5: ABOUT =====
            with gr.Tab("About"):
                gr.Markdown(f"""
                # SciTrans-LLMs System Information
                
                **Version:** {__version__}  
                **Author:** Franck Davy  
                **Institution:** Wenzhou University  
                **Year:** 2025
                
                ## 🎯 Research Contributions
                
                1. **Adaptive Translation Strategy** — Pre-scoring drives parameter adaptation
                2. **Multi-Dimensional Scoring** — 5-dimensional quality assessment
                3. **Repair-Driven Workflow** — Selective block repair (10× efficiency)
                4. **Cascade-Free Backend** — Ensemble + reranking at $0 cost
                5. **Integrated Scoring Pipeline** — End-to-end QA system
                
                ## ✨ Features
                
                - ✅ Multi-column layout preservation
                - ✅ Math-safe translation (equations protected)
                - ✅ Table-safe handling
                - ✅ Context-aware translation
                - ✅ Multi-candidate reranking
                - ✅ Automatic quality scoring
                - ✅ Selective repair workflow
                - ✅ Translation caching
                
                ## 🔧 Available Backends
                
                | Backend | Type | Cost | Quality |
                |---------|------|------|---------|
                | cascade_free | Ensemble | Free | ⭐⭐⭐⭐⭐ |
                | deepseek | API | Free Tier | ⭐⭐⭐⭐⭐ |
                | anthropic | API | Paid | ⭐⭐⭐⭐⭐ |
                | openai | API | Paid | ⭐⭐⭐⭐ |
                | google | API | Free | ⭐⭐⭐ |
                | ollama | Local | Free | ⭐⭐⭐ |
                
                ## 📧 Contact
                
                **Email:** aknk.v@pm.me  
                **Institution:** Wenzhou University, 2025
                """)

    return app


def launch_gui(share: bool = False, server_port: int = 7860):
    """Launch the SciTrans GUI."""
    logger.info("Starting SciTrans GUI...")
    logger.info(f"Version: {__version__}")
    logger.info(f"Server port: {server_port}")

    app = create_gui()
    app.launch(share=share, server_port=server_port, show_error=True)


if __name__ == "__main__":
    launch_gui()
