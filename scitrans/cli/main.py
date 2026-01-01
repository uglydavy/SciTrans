from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from scitrans.logging_config import setup_logging
from scitrans.pipeline import PipelineConfig, repair_failed_blocks, run_pipeline
from scitrans.translation.backends.anthropic_backend import AnthropicBackend
from scitrans.translation.backends.cascade_free import CascadeFreeBackend
from scitrans.translation.backends.deepseek_backend import DeepSeekBackend
from scitrans.translation.backends.dummy import DummyBackend
from scitrans.translation.backends.google_backend import GoogleTranslateBackend
from scitrans.translation.backends.huggingface_backend import HuggingFaceBackend
from scitrans.translation.backends.ollama_backend import OllamaBackend
from scitrans.translation.backends.openai_backend import OpenAIBackend
from scitrans.utils.backend_checker import get_all_backends_status, validate_backend_before_use
from scitrans.utils.env_loader import load_environment_variables

app = typer.Typer(
    add_completion=False,
    help="SciTrans-LLMs — Adaptive Scientific PDF Translation System",
    rich_markup_mode="rich",
)
console = Console()


def _get_backend(name: str, model: str):
    name = name.lower().strip()
    if name == "cascade_free":
        return CascadeFreeBackend(model=model)
    if name == "dummy":
        return DummyBackend(model=model)
    if name == "deepseek":
        return DeepSeekBackend(model=model)
    if name == "anthropic":
        return AnthropicBackend(model=model)
    if name in ("openai", "gpt", "cascade"):
        return OpenAIBackend(model=model)
    if name in ("google", "google_free"):
        return GoogleTranslateBackend(model=model)
    if name in ("huggingface", "hf"):
        return HuggingFaceBackend(model=model)
    if name == "ollama":
        return OllamaBackend(model=model)
    raise typer.BadParameter(
        f"Unknown backend: {name}. Available: cascade_free (default), deepseek, anthropic, openai, google, huggingface, ollama, dummy"
    )


@app.command()
def gui(
    share: bool = typer.Option(False, "--share", help="Create public share link"),
    port: int = typer.Option(7860, "--port", help="Server port"),
):
    """Launch the SciTrans web GUI."""
    try:
        from scitrans.gui import launch_gui
    except ImportError as e:
        console.print(
            "[red]GUI not available. Install with: pip install -e '.[gui]' or pip install gradio[/red]"
        )
        raise typer.Exit(1) from e

    console.print("[bold cyan]🚀 Launching SciTrans GUI...[/bold cyan]")
    console.print(f"[green]Open your browser to: http://localhost:{port}[/green]")
    launch_gui(share=share, server_port=port)


@app.command()
def translate(
    in_pdf: str = typer.Option(..., "--in", help="Input PDF path"),
    out_pdf: str = typer.Option(..., "--out", help="Output translated PDF path"),
    source: str = typer.Option("en", "--source", help="Source language"),
    target: str = typer.Option("fr", "--target", help="Target language"),
    backend: str = typer.Option(
        "cascade_free",
        "--backend",
        help="Backend: cascade_free (default), anthropic, openai, google, huggingface, ollama, dummy",
    ),
    model: str = typer.Option("cascade_free", "--model", help="Model name"),
    out_dir: str = typer.Option("outputs", "--artifacts", help="Artifacts output directory"),
    n_candidates: int = typer.Option(
        3, "--n-candidates", help="Number of translation candidates (default: 3 for quality)"
    ),
    context_window: int = typer.Option(
        2, "--context", help="Number of previous blocks for context (default: 2)"
    ),
    no_cache: bool = typer.Option(False, "--no-cache", help="Disable translation caching"),
    no_rerank: bool = typer.Option(
        False, "--no-rerank", help="Disable candidate reranking (NOT RECOMMENDED)"
    ),
    no_retry: bool = typer.Option(
        False, "--no-retry", help="Disable automatic retry on failures (NOT RECOMMENDED)"
    ),
    render_mode: str = typer.Option(
        "perfect",
        "--render-mode",
        help="Render mode: perfect (exact font sizes, bullets), enhanced (preserve styling), auto (detect math), math-aware (preserve equations), math-safe (legacy) [default: perfect]",
    ),
    translate_tables: bool = typer.Option(
        False,
        "--translate-tables/--preserve-tables",
        help="Translate tables instead of preserving them",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output (INFO level)"),
    debug: bool = typer.Option(False, "--debug", help="Debug output (DEBUG level, detailed logs)"),
    log_file: str = typer.Option(None, "--log-file", help="Write logs to file"),
    parallel: bool = typer.Option(
        False, "--parallel", help="Enable parallel block translation (experimental)"
    ),
    max_workers: int = typer.Option(4, "--max-workers", help="Max parallel workers (default: 4)"),
):
    """
    Translate a PDF document from source language to target language.

    Examples:
        # Basic translation (English to French)
        scitrans translate --in document.pdf --out document_fr.pdf

        # Use specific backend
        scitrans translate --in doc.pdf --out doc_fr.pdf --backend anthropic --model claude-3-5-sonnet-20241022

        # High quality with perfect rendering
        scitrans translate --in doc.pdf --out doc_fr.pdf --render-mode perfect --n-candidates 5

        # Fast translation (fewer candidates, no reranking)
        scitrans translate --in doc.pdf --out doc_fr.pdf --n-candidates 1 --no-rerank
    """
    # Load environment variables
    load_environment_variables()

    # Validate inputs
    in_path = Path(in_pdf)
    if not in_path.exists():
        console.print(f"[red]Error: Input PDF not found: {in_pdf}[/red]")
        raise typer.Exit(1)

    if not in_path.suffix.lower() == ".pdf":
        console.print(f"[red]Error: Input file must be a PDF: {in_pdf}[/red]")
        raise typer.Exit(1)

    # Validate backend before proceeding
    is_valid, error_msg = validate_backend_before_use(backend)
    if not is_valid:
        console.print(f"[red]Backend '{backend}' is not available:[/red]")
        console.print(f"[red]{error_msg}[/red]")
        console.print("\n[yellow]Run 'scitrans backends' to see available backends[/yellow]")
        raise typer.Exit(1)

    # Setup logging
    if debug:
        setup_logging(level="DEBUG", debug=True, log_file=Path(log_file) if log_file else None)
    elif verbose:
        setup_logging(level="INFO", debug=False, log_file=Path(log_file) if log_file else None)
    else:
        setup_logging(level="WARNING", debug=False, log_file=Path(log_file) if log_file else None)

    # Show configuration
    console.print("\n[bold cyan]Translation Configuration[/bold cyan]")
    console.print(f"  Input: {in_pdf}")
    console.print(f"  Output: {out_pdf}")
    console.print(f"  Languages: {source} → {target}")
    console.print(f"  Backend: {backend} ({model})")
    console.print(f"  Render Mode: {render_mode}")
    console.print()

    cfg = PipelineConfig(
        source_lang=source,
        target_lang=target,
        model=model,
        output_dir=out_dir,
        n_candidates=n_candidates,
        context_window=context_window,
        use_cache=not no_cache,
        enable_reranking=not no_rerank,  # ON by default (innovation)
        retry_failed=not no_retry,  # ON by default (innovation)
        render_mode=render_mode,  # auto/math-aware/math-safe
        translate_tables=translate_tables,
        parallel_translation=parallel,  # Parallel translation
        max_workers=max_workers,  # Max workers for parallel
    )
    # Choose backend-specific default model if caller left default "cascade_free"
    chosen_model = model
    backend_norm = backend.lower().strip()
    # Prefer free/cheap defaults unless user overrides
    if model == "cascade_free":
        if backend_norm == "deepseek":
            chosen_model = "deepseek-chat"
        elif backend_norm == "anthropic":
            chosen_model = "claude-3-5-sonnet-20241022"
        elif backend_norm in ("openai", "gpt", "cascade"):
            chosen_model = "gpt-4o-mini"  # Cheap OpenAI model
        elif backend_norm == "dummy":
            chosen_model = "dummy"
        else:
            # cascade_free remains cascade_free; google/hf/ollama ignore model here
            chosen_model = model

    be = _get_backend(backend, model=chosen_model)

    # Update cfg model to chosen_model for consistency
    cfg = PipelineConfig(
        source_lang=cfg.source_lang,
        target_lang=cfg.target_lang,
        model=chosen_model,
        temperature=cfg.temperature,
        n_candidates=cfg.n_candidates,
        output_dir=cfg.output_dir,
        assets_dir=cfg.assets_dir,
        render=cfg.render,
        render_mode=cfg.render_mode,
        translate_tables=cfg.translate_tables,
        use_cache=cfg.use_cache,
        context_window=cfg.context_window,
        enable_reranking=cfg.enable_reranking,
        retry_failed=cfg.retry_failed,
        parallel_translation=cfg.parallel_translation,
        max_workers=cfg.max_workers,
    )

    # Run pipeline with progress indicator
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Translating PDF...", total=100)

        # Run pipeline (progress is handled internally by pipeline)
        try:
            report = run_pipeline(input_pdf=in_pdf, output_pdf=out_pdf, backend=be, cfg=cfg)
            progress.update(task, completed=100)
        except KeyboardInterrupt:
            console.print("\n[yellow]Translation interrupted by user[/yellow]")
            raise typer.Exit(1) from None
        except Exception as e:
            console.print(f"\n[red]Translation failed: {e}[/red]")
            if debug:
                import traceback

                console.print(f"[red]{traceback.format_exc()}[/red]")
            raise typer.Exit(1) from None

    # Format and display results
    console.print("\n[bold green]✓ Translation Complete![/bold green]\n")

    # Create summary table
    summary_table = Table(title="Translation Summary", show_header=True, header_style="bold cyan")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="green")

    summary_table.add_row("Output PDF", out_pdf)
    summary_table.add_row("Backend", report.get("backend", "unknown"))
    summary_table.add_row("Model", report.get("model", "unknown"))
    summary_table.add_row("Total Blocks", str(report.get("num_blocks", 0)))
    summary_table.add_row("Successful", f"{report.get('num_ok', 0)}")
    summary_table.add_row("Failed", f"{report.get('num_failed', 0)}")
    summary_table.add_row("Time", f"{report.get('elapsed_s', 0):.1f}s")

    scoring = report.get("scoring", {})
    summary_table.add_row("Document Quality", f"{scoring.get('document_quality', 0):.1%}")
    summary_table.add_row("Confidence", f"{scoring.get('document_confidence', 0):.1%}")
    summary_table.add_row("Acceptance Rate", f"{scoring.get('acceptance_rate', 0):.1%}")

    console.print(summary_table)

    # Show artifacts location
    artifacts_dir = report.get("artifacts_dir", "")
    if artifacts_dir:
        console.print(f"\n[dim]Artifacts saved to: {artifacts_dir}[/dim]")

    # Show failed blocks if any
    failed_blocks = report.get("health", {}).get("failed_block_ids", [])
    if failed_blocks:
        console.print(
            f"\n[yellow]⚠️  {len(failed_blocks)} blocks failed. Use 'scitrans repair' to fix them.[/yellow]"
        )
        console.print(
            f"[dim]  scitrans repair --in {in_pdf} --out {out_pdf} --artifacts {artifacts_dir}[/dim]"
        )


@app.command()
def repair(
    in_pdf: str = typer.Option(..., "--in", help="Input PDF path"),
    out_pdf: str = typer.Option(..., "--out", help="Output repaired PDF path"),
    artifacts_dir: str = typer.Option(
        ..., "--artifacts", help="Artifacts directory from previous run"
    ),
    backend: str = typer.Option("cascade_free", "--backend", help="Backend name"),
    model: str = typer.Option("cascade_free", "--model", help="Model name"),
    block_ids: str = typer.Option(
        None, "--blocks", help="Comma-separated block IDs to repair (default: all failed)"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """
    Repair failed blocks from a previous translation run.

    Examples:
        # Repair all failed blocks
        scitrans repair --in doc.pdf --out doc_fixed.pdf --artifacts outputs/doc

        # Repair specific blocks
        scitrans repair --in doc.pdf --out doc_fixed.pdf --artifacts outputs/doc --blocks b_0_abc,b_1_def
    """
    load_environment_variables()

    # Validate inputs
    if not Path(in_pdf).exists():
        console.print(f"[red]Error: Input PDF not found: {in_pdf}[/red]")
        raise typer.Exit(1)

    if not Path(artifacts_dir).exists():
        console.print(f"[red]Error: Artifacts directory not found: {artifacts_dir}[/red]")
        raise typer.Exit(1)

    # Setup logging
    if verbose:
        setup_logging(level="INFO")
    else:
        setup_logging(level="WARNING")

    cfg = PipelineConfig(model=model)
    be = _get_backend(backend, model=model)

    block_id_list = [bid.strip() for bid in block_ids.split(",")] if block_ids else None

    console.print("\n[bold cyan]Repairing Translation[/bold cyan]\n")
    console.print(f"  Input: {in_pdf}")
    console.print(f"  Output: {out_pdf}")
    console.print(f"  Artifacts: {artifacts_dir}")
    console.print(f"  Backend: {backend} ({model})")
    if block_id_list:
        console.print(f"  Blocks: {len(block_id_list)} specified")
    else:
        console.print("  Blocks: All failed blocks")
    console.print()

    report = repair_failed_blocks(
        input_pdf=in_pdf,
        output_pdf=out_pdf,
        artifacts_dir=artifacts_dir,
        backend=be,
        cfg=cfg,
        block_ids=block_id_list,
    )

    # Format results
    console.print("\n[bold green]✓ Repair Complete![/bold green]\n")

    repair_table = Table(show_header=True, header_style="bold cyan")
    repair_table.add_column("Metric", style="cyan")
    repair_table.add_column("Value", style="green")

    repair_table.add_row("Repaired", str(report.get("repaired", 0)))
    repair_table.add_row("Still Failed", str(report.get("still_failed", 0)))
    repair_table.add_row("Total Attempted", str(report.get("total_attempted", 0)))

    console.print(repair_table)


@app.command()
def backends():
    """List all available translation backends with detailed status."""
    load_environment_variables()

    console.print("\n[bold cyan]Available Translation Backends[/bold cyan]\n")

    # Get comprehensive status
    all_statuses = get_all_backends_status()

    # Create table
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Backend", style="cyan", width=15)
    table.add_column("Description", style="white", width=35)
    table.add_column("Cost", style="dim", width=12)
    table.add_column("Status", width=25)

    backends_info = [
        ("cascade_free", "Ensemble (DeepSeek + Google + Ollama)", "Free", "Default (recommended)"),
        ("deepseek", "DeepSeek Chat", "Free tier", ""),
        ("anthropic", "Claude 3.5 Sonnet", "Paid", ""),
        ("openai", "GPT-4 / GPT-4o", "Paid", ""),
        ("google", "Google Translate", "Free", ""),
        ("huggingface", "HuggingFace Models", "Free", ""),
        ("ollama", "Local LLMs", "Free (local)", ""),
        ("dummy", "Identity (testing)", "Free", "Testing only"),
    ]

    for name, desc, cost, default_note in backends_info:
        status = all_statuses.get(name, {})

        if status.get("available") and status.get("health") == "healthy":
            status_text = "[green]✅ Available[/green]"
        elif not status.get("dependencies_ok"):
            deps = status.get("missing_dependencies", [])
            status_text = f"[red]❌ Missing: {deps[0][:20] if deps else 'dependencies'}[/red]"
        elif not status.get("env_vars_ok"):
            vars_missing = status.get("missing_env_vars", [])
            status_text = f"[yellow]⚠️  Need: {', '.join(vars_missing)}[/yellow]"
        else:
            status_text = f"[red]❌ {status.get('error', 'Error')[:20]}[/red]"

        if default_note:
            status_text += f" [dim]({default_note})[/dim]"

        table.add_row(name, desc, cost, status_text)

    console.print(table)
    console.print("\n[dim]Usage: scitrans translate --in doc.pdf --backend cascade_free[/dim]")
    console.print("[dim]Run 'scitrans status' for detailed backend health check[/dim]")


@app.command()
def info(pdf: str = typer.Argument(None, help="PDF file to analyze (optional)")):
    """Show system information or analyze a PDF."""
    if pdf:
        # Analyze PDF
        pdf_path = Path(pdf)
        if not pdf_path.exists():
            console.print(f"[red]Error: PDF not found: {pdf}[/red]")
            raise typer.Exit(1)

        from scitrans.parsing.pymupdf_parser import parse_pdf

        console.print(f"\n[bold cyan]PDF Analysis: {pdf}[/bold cyan]\n")

        with console.status("[cyan]Parsing PDF...[/cyan]"):
            doc = parse_pdf(pdf)

        # Create analysis table
        analysis_table = Table(show_header=True, header_style="bold cyan")
        analysis_table.add_column("Metric", style="cyan")
        analysis_table.add_column("Value", style="green")

        total_blocks = sum(len(p.blocks) for p in doc.pages)
        text_blocks = sum(1 for p in doc.pages for b in p.blocks if b.type == "text")
        math_blocks = sum(1 for p in doc.pages for b in p.blocks if b.type == "equation")
        tables = sum(1 for p in doc.pages for b in p.blocks if b.meta.get("region") == "table")

        analysis_table.add_row("Pages", str(len(doc.pages)))
        analysis_table.add_row("Total Blocks", str(total_blocks))
        analysis_table.add_row("Text Blocks", str(text_blocks))
        analysis_table.add_row("Math Blocks", str(math_blocks))
        analysis_table.add_row("Tables", str(tables))
        analysis_table.add_row(
            "Images", str(sum(1 for p in doc.pages for b in p.blocks if b.type == "image"))
        )

        console.print(analysis_table)

        # File size
        file_size = pdf_path.stat().st_size
        console.print(f"\n[dim]File size: {file_size / 1024:.1f} KB[/dim]")
    else:
        # System info
        from scitrans import __version__

        console.print("\n[bold cyan]SciTrans-LLMs System Information[/bold cyan]\n")

        info_table = Table(show_header=False, box=None)
        info_table.add_column("Label", style="cyan", width=20)
        info_table.add_column("Value", style="white")

        info_table.add_row("Version", __version__)
        info_table.add_row("Author", "Franck Davy")
        info_table.add_row("Institution", "Wenzhou University, 2025")
        info_table.add_row(
            "Thesis", "Adaptive Document Translation Enhanced by Technology based on LLMs"
        )

        console.print(info_table)
        console.print("\n[dim]Commands:[/dim]")
        console.print("  [dim]scitrans backends[/dim]  - List available backends")
        console.print("  [dim]scitrans status[/dim]    - Check system status")
        console.print("  [dim]scitrans info <pdf>[/dim] - Analyze a PDF")


@app.command()
def status():
    """Check system status: backends, dependencies, and configuration."""
    load_environment_variables()

    console.print("\n[bold cyan]SciTrans System Status[/bold cyan]\n")

    # Get all backend statuses
    all_statuses = get_all_backends_status()

    # Categorize backends
    healthy = []
    missing_deps = []
    missing_keys = []
    errors = []

    for backend, status in all_statuses.items():
        if status.get("available") and status.get("health") == "healthy":
            healthy.append(backend)
        elif not status.get("dependencies_ok"):
            missing_deps.append((backend, status))
        elif not status.get("env_vars_ok"):
            missing_keys.append((backend, status))
        else:
            errors.append((backend, status))

    # Summary
    console.print(f"[green]✅ Healthy Backends: {len(healthy)}/{len(all_statuses)}[/green]")
    if healthy:
        console.print(f"   {', '.join(healthy)}\n")

    if missing_deps:
        console.print(f"[red]❌ Missing Dependencies: {len(missing_deps)}[/red]")
        for backend, status in missing_deps:
            deps = status.get("missing_dependencies", [])
            console.print(f"   [red]{backend}:[/red] {deps[0] if deps else 'Unknown'}")
        console.print()

    if missing_keys:
        console.print(f"[yellow]⚠️  Missing API Keys: {len(missing_keys)}[/yellow]")
        for backend, status in missing_keys:
            vars_missing = status.get("missing_env_vars", [])
            console.print(f"   [yellow]{backend}:[/yellow] {', '.join(vars_missing)}")
        console.print()

    if errors:
        console.print(f"[red]❌ Errors: {len(errors)}[/red]")
        for backend, status in errors:
            error = status.get("error", "Unknown error")
            console.print(f"   [red]{backend}:[/red] {error[:60]}")
        console.print()

    # Environment check
    console.print("[bold cyan]Environment:[/bold cyan]")
    env_file = Path("setup_env.sh")
    if env_file.exists():
        console.print("  [green]✅ setup_env.sh found[/green]")
    else:
        console.print("  [yellow]⚠️  setup_env.sh not found[/yellow]")

    # Overall status
    if len(healthy) >= 5:
        console.print("\n[bold green]✅ System is ready for translation![/bold green]")
    elif len(healthy) > 0:
        console.print(
            "\n[yellow]⚠️  System partially ready ({len(healthy)}/{len(all_statuses)} backends)[/yellow]"
        )
    else:
        console.print("\n[red]❌ No backends available. Run 'scitrans backends' for details.[/red]")

    console.print()


@app.command()
def batch(
    input_dir: str = typer.Option(
        ..., "--input-dir", help="Directory containing PDFs to translate"
    ),
    output_dir: str = typer.Option(
        ..., "--output-dir", help="Output directory for translated PDFs"
    ),
    source: str = typer.Option("en", "--source", help="Source language"),
    target: str = typer.Option("fr", "--target", help="Target language"),
    backend: str = typer.Option("cascade_free", "--backend", help="Translation backend"),
    model: str = typer.Option("cascade_free", "--model", help="Model name"),
    render_mode: str = typer.Option("perfect", "--render-mode", help="Render mode"),
    pattern: str = typer.Option("*.pdf", "--pattern", help="File pattern to match"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """
    Batch translate multiple PDFs from a directory.

    Examples:
        # Translate all PDFs in a directory
        scitrans batch --input-dir ./documents --output-dir ./translated

        # Translate with specific backend
        scitrans batch --input-dir ./docs --output-dir ./translated --backend anthropic
    """
    from pathlib import Path

    load_environment_variables()

    input_path = Path(input_dir)
    output_path = Path(output_dir)

    if not input_path.exists():
        console.print(f"[red]Error: Input directory not found: {input_dir}[/red]")
        raise typer.Exit(1)

    output_path.mkdir(parents=True, exist_ok=True)

    # Find all PDFs
    pdf_files = list(input_path.glob(pattern))

    if not pdf_files:
        console.print(f"[yellow]No PDFs found matching pattern '{pattern}' in {input_dir}[/yellow]")
        raise typer.Exit(0)

    console.print("\n[bold cyan]Batch Translation[/bold cyan]")
    console.print(f"  Input Directory: {input_dir}")
    console.print(f"  Output Directory: {output_dir}")
    console.print(f"  Files Found: {len(pdf_files)}")
    console.print(f"  Backend: {backend} ({model})")
    console.print()

    # Validate backend
    is_valid, error_msg = validate_backend_before_use(backend)
    if not is_valid:
        console.print(f"[red]Backend '{backend}' is not available:[/red]")
        console.print(f"[red]{error_msg}[/red]")
        raise typer.Exit(1)

    # Setup logging
    if verbose:
        setup_logging(level="INFO")
    else:
        setup_logging(level="WARNING")

    from scitrans.cli.main import _get_backend
    from scitrans.pipeline import PipelineConfig, run_pipeline

    be = _get_backend(backend, model=model)
    cfg = PipelineConfig(
        source_lang=source,
        target_lang=target,
        model=model,
        render_mode=render_mode,
    )

    # Process each PDF
    successful = 0
    failed = 0

    for i, pdf_file in enumerate(pdf_files, 1):
        console.print(f"[cyan][{i}/{len(pdf_files)}] Processing: {pdf_file.name}[/cyan]")

        output_file = output_path / f"{pdf_file.stem}_translated.pdf"

        try:
            report = run_pipeline(
                input_pdf=str(pdf_file), output_pdf=str(output_file), backend=be, cfg=cfg
            )

            if report.get("num_ok", 0) > 0:
                console.print(f"  [green]✅ Success: {output_file.name}[/green]")
                successful += 1
            else:
                console.print(f"  [yellow]⚠️  No blocks translated: {pdf_file.name}[/yellow]")
                failed += 1

        except Exception as e:
            console.print(f"  [red]❌ Failed: {pdf_file.name} - {e}[/red]")
            failed += 1

    # Summary
    console.print("\n[bold green]Batch Translation Complete![/bold green]\n")

    summary_table = Table(show_header=True, header_style="bold cyan")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="green")

    summary_table.add_row("Total Files", str(len(pdf_files)))
    summary_table.add_row("Successful", str(successful))
    summary_table.add_row("Failed", str(failed))

    console.print(summary_table)


@app.command()
def export(
    artifacts_dir: str = typer.Option(
        ..., "--artifacts", help="Artifacts directory from translation"
    ),
    output_format: str = typer.Option("json", "--format", help="Export format: json, word, latex"),
    output_file: str = typer.Option(None, "--out", help="Output file path"),
):
    """
    Export translations to different formats.

    Examples:
        # Export to JSON
        scitrans export --artifacts outputs/document --format json

        # Export to Word
        scitrans export --artifacts outputs/document --format word --out document.docx
    """
    import json
    from pathlib import Path

    artifacts_path = Path(artifacts_dir)
    if not artifacts_path.exists():
        console.print(f"[red]Error: Artifacts directory not found: {artifacts_dir}[/red]")
        raise typer.Exit(1)

    translations_file = artifacts_path / "translations.json"
    if not translations_file.exists():
        console.print(f"[red]Error: translations.json not found in {artifacts_dir}[/red]")
        raise typer.Exit(1)

    # Load translations
    translations_data = json.loads(translations_file.read_text())
    translations = {tb["block_id"]: tb["translated_text"] for tb in translations_data}

    # Determine output file
    if not output_file:
        output_file = str(artifacts_path / f"export.{output_format}")

    # Export
    if output_format == "json":
        from scitrans.export.json_export import export_to_json

        success = export_to_json(translations, "", output_file)
    elif output_format == "word":
        from scitrans.export.word import export_to_word

        success = export_to_word(translations, "", output_file)
    elif output_format == "latex":
        from scitrans.export.latex import export_to_latex

        success = export_to_latex(translations, "", output_file)
    else:
        console.print(f"[red]Error: Unsupported format: {output_format}[/red]")
        raise typer.Exit(1)

    if success:
        console.print(f"[green]✅ Exported to {output_file}[/green]")
    else:
        console.print("[red]❌ Export failed[/red]")
        raise typer.Exit(1)


@app.command()
def api(
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", help="Port to bind to"),
):
    """
    Start the REST API server.

    Examples:
        # Start API server
        scitrans api

        # Start on custom port
        scitrans api --port 8080
    """
    try:
        from scitrans.api.server import run_api_server

        console.print(f"[cyan]🚀 Starting SciTrans API server on {host}:{port}[/cyan]")
        run_api_server(host=host, port=port)
    except ImportError:
        console.print(
            "[red]Error: FastAPI not installed. Install with: pip install fastapi uvicorn[/red]"
        )
        raise typer.Exit(1) from None


if __name__ == "__main__":
    app()
