#!/usr/bin/env python3
"""Interactive API key setup script for SciTrans.

This script helps you configure API keys for various translation backends.
"""

import json
from pathlib import Path


def get_config_path() -> Path:
    """Get path to .scitrans_backends.json in project root."""
    # Assume script is in scripts/, so project root is parent
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    return project_root / ".scitrans_backends.json"


def load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(path: Path, cfg: dict) -> None:
    path.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def prompt_api_key(
    backend_name: str, description: str, current_value: str | None
) -> str | None:
    """Prompt user for an API key."""
    print(f"\n{'=' * 60}")
    print(f"{backend_name}")
    print(f"{'=' * 60}")
    print(f"{description}")

    if current_value:
        print(
            f"\nCurrently set: {current_value[:10]}..."
            if len(current_value) > 10
            else f"\nCurrently set: {current_value}"
        )
        prompt = "Enter new value (or press Enter to keep current): "
    else:
        prompt = "Enter API key (or press Enter to skip): "

    value = input(prompt).strip()

    if not value and current_value:
        return current_value

    return value if value else None


def main():
    print("SciTrans API Key Setup")
    print("=" * 60)
    print("\nThis script will help you configure API keys for translation backends.")
    print("You can skip any backend by pressing Enter.\n")

    config_path = get_config_path()
    cfg = load_config(config_path)

    # Anthropic (Claude)
    anthropic_key = prompt_api_key(
        "Anthropic (Claude)",
        "Get your key at: https://console.anthropic.com/",
        cfg.get("anthropic", {}).get("api_key"),
    )
    if anthropic_key:
        cfg.setdefault("anthropic", {})["api_key"] = anthropic_key

    # OpenAI / Cascade
    openai_key = prompt_api_key(
        "OpenAI / Cascade",
        "Get your key at: https://platform.openai.com/api-keys\n"
        "Or use Cascade/TogetherAI/etc. with OPENAI_BASE_URL",
        cfg.get("openai", {}).get("api_key"),
    )
    if openai_key:
        cfg.setdefault("openai", {})["api_key"] = openai_key

        # Optional: custom base URL
        base_url = input("\nCustom API base URL (optional, press Enter to skip): ").strip()
        if base_url:
            cfg.setdefault("openai", {})["base_url"] = base_url

    # HuggingFace
    hf_key = prompt_api_key(
        "HuggingFace",
        "Get your key at: https://huggingface.co/settings/tokens\n"
        "(Optional for free tier, required for faster endpoints)",
        cfg.get("huggingface", {}).get("api_key"),
    )
    if hf_key:
        cfg.setdefault("huggingface", {})["api_key"] = hf_key

    # DeepSeek
    deepseek_key = prompt_api_key(
        "DeepSeek",
        "Get your key at: https://platform.deepseek.com/",
        cfg.get("deepseek", {}).get("api_key"),
    )
    if deepseek_key:
        cfg.setdefault("deepseek", {})["api_key"] = deepseek_key

    # Google AI (Gemini)
    google_ai_key = prompt_api_key(
        "Google AI (Gemini)",
        "Get your key at: https://aistudio.google.com/api-keys",
        cfg.get("google_ai", {}).get("api_key"),
    )
    if google_ai_key:
        cfg.setdefault("google_ai", {})["api_key"] = google_ai_key

    # Ollama (local, no API key)
    print(f"\n{'=' * 60}")
    print("Ollama (Local)")
    print(f"{'=' * 60}")
    print("Ollama runs locally and doesn't require an API key.")
    print("Install from: https://ollama.ai/")
    ollama_host = input("Ollama host (default: http://localhost:11434): ").strip()
    if ollama_host:
        cfg.setdefault("ollama", {})["host"] = ollama_host

    # Google Translate (free, no API key)
    print(f"\n{'=' * 60}")
    print("Google Translate (Free)")
    print(f"{'=' * 60}")
    print("The free Google Translate backend doesn't require an API key.")
    print("It's rate-limited and may be unreliable for production use.")

    # Save .env file
    print(f"\n{'=' * 60}")
    print("Summary")
    print(f"{'=' * 60}")
    print(f"\nAPI keys will be saved to: {config_path}")
    print(f"Backends configured: {len([k for k in cfg.keys()])}")

    save_choice = input("\nSave configuration? (y/n): ").strip().lower()

    if save_choice == "y":
        save_config(config_path, cfg)
        print(f"\n✓ Configuration saved to {config_path}")
    else:
        print("\nConfiguration not saved.")

    print("\nDone! You can now use SciTrans with your configured backends.")


if __name__ == "__main__":
    main()
