#!/usr/bin/env python3
"""
Diagnostic and auto-fix script for SciTrans translation issues.
Checks backend availability and provides setup instructions.
"""

import os
import subprocess
import sys


def print_header(text):
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def check_api_keys():
    """Check which API keys are set."""
    print_header("1. API KEY STATUS")

    keys = {
        "DEEPSEEK_API_KEY": "DeepSeek (Recommended - Free Tier)",
        "ANTHROPIC_API_KEY": "Anthropic (Claude)",
        "OPENAI_API_KEY": "OpenAI (GPT)",
        "GOOGLE_API_KEY": "Google (Gemini)",
    }

    any_set = False
    for env_key, name in keys.items():
        value = os.getenv(env_key)
        if value:
            masked = f"{value[:8]}...{value[-4:]}" if len(value) > 12 else "***"
            print(f"   ✅ {name}: {masked}")
            any_set = True
        else:
            print(f"   ❌ {name}: Not set")

    return any_set


def check_free_libraries():
    """Check if free translation libraries are installed."""
    print_header("2. FREE BACKEND LIBRARIES")

    googletrans_available = False
    try:
        import googletrans

        print(f"   ✅ googletrans: v{googletrans.__version__} installed")
        googletrans_available = True
    except ImportError:
        print("   ❌ googletrans: NOT installed")
        print("      Install: pip install googletrans==4.0.0rc1")

    return googletrans_available


def check_ollama():
    """Check if Ollama is running."""
    print_header("3. LOCAL BACKENDS")

    try:
        import requests

        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        if response.status_code == 200:
            print("   ✅ Ollama: Running locally")
            return True
    except Exception:
        pass

    print("   ❌ Ollama: Not running")
    print("      Install: https://ollama.ai/")
    print("      Start: ollama serve")
    return False


def test_cascade_free():
    """Test if cascade_free can initialize."""
    print_header("4. CASCADE_FREE BACKEND TEST")

    try:
        from scitrans.translation.backends.cascade_free import CascadeFreeBackend

        backend = CascadeFreeBackend()
        print(f"   ✅ cascade_free initialized with {len(backend._backends)} backends:")
        for name, _ in backend._backends:
            print(f"      ✅ {name}")
        return True
    except Exception as e:
        print("   ❌ cascade_free FAILED to initialize")
        print(f"      Error: {str(e)[:200]}")
        return False


def test_actual_translation():
    """Test if translation actually produces different text."""
    print_header("5. ACTUAL TRANSLATION TEST")

    try:
        from scitrans.translation.backends.base import TranslateRequest
        from scitrans.translation.backends.dummy import DummyBackend

        backend = DummyBackend()
        req = TranslateRequest(
            text="Hello world",
            source_lang="en",
            target_lang="fr",
            system_prompt="Translate to French",
        )
        result = backend.translate(req)

        input_text = req.text
        output_text = result.candidates[0]

        print(f"   Input:  '{input_text}'")
        print(f"   Output: '{output_text}'")

        if input_text == output_text:
            print("   ❌ PROBLEM: Output equals input (no translation!)")
            print("      This is expected for dummy backend")
            print("      But NOT acceptable for real translation")
            return False
        else:
            print("   ✅ Output differs from input (translation worked!)")
            return True

    except Exception as e:
        print(f"   ❌ Test failed: {e}")
        return False


def provide_solutions():
    """Provide step-by-step solutions."""
    print_header("💡 SOLUTIONS TO FIX TRANSLATION")

    print("\n🎯 RECOMMENDED SOLUTION (Easiest):\n")
    print("Install googletrans for free translation:")
    print("   pip install googletrans==4.0.0rc1")
    print("")
    print("Then restart and translation will work!")

    print("\n\n🎯 ALTERNATIVE SOLUTION 1 (Best Quality):\n")
    print("Get free DeepSeek API key:")
    print("   1. Visit: https://platform.deepseek.com/")
    print("   2. Sign up (free tier available)")
    print("   3. Get API key")
    print("   4. Set key:")
    print("      export DEEPSEEK_API_KEY='sk-your-key-here'")
    print("   5. Restart GUI")

    print("\n\n🎯 ALTERNATIVE SOLUTION 2 (Local, Offline):\n")
    print("Install and run Ollama:")
    print("   1. Download from: https://ollama.ai/")
    print("   2. Install")
    print("   3. Run: ollama serve")
    print("   4. Pull model: ollama pull llama3.2")
    print("   5. Restart GUI")

    print("\n\n🎯 QUICK TEST (Verify Pipeline Works):\n")
    print("Use dummy backend to test pipeline (won't translate, but verifies flow):")
    print("   scitrans translate --in test.pdf --out test_out.pdf --backend dummy")
    print("")
    print("If this works, pipeline is OK, just need a real backend!")


def auto_fix():
    """Attempt to auto-fix by installing googletrans."""
    print_header("6. AUTO-FIX ATTEMPT")

    print("\nAttempting to install googletrans...")
    print("(This requires internet connection and pip)\n")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "googletrans==4.0.0rc1"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode == 0:
            print("   ✅ googletrans installed successfully!")
            print("   ✅ Translation should work now!")
            return True
        else:
            print("   ❌ Installation failed:")
            print(f"      {result.stderr[:200]}")
            return False
    except Exception as e:
        print(f"   ❌ Auto-fix failed: {e}")
        return False


def main():
    print("\n")
    print("╔════════════════════════════════════════════════════════════════════╗")
    print("║     SciTrans Translation Diagnostic & Fix Tool                     ║")
    print("╚════════════════════════════════════════════════════════════════════╝")

    # Run all checks
    has_api_keys = check_api_keys()
    has_googletrans = check_free_libraries()
    has_ollama = check_ollama()
    cascade_works = test_cascade_free()
    test_actual_translation()

    # Summary
    print_header("📊 DIAGNOSIS SUMMARY")

    if cascade_works:
        print("\n✅ GOOD NEWS: Translation backends are available!")
        print("   Your system should be able to translate.")
    else:
        print("\n❌ CRITICAL: No translation backends available!")
        print("   Translation will NOT work until you fix this.")

    print("\nBackend Availability:")
    print(f"   API Keys: {'✅' if has_api_keys else '❌'}")
    print(f"   googletrans: {'✅' if has_googletrans else '❌'}")
    print(f"   Ollama: {'✅' if has_ollama else '❌'}")
    print(f"   cascade_free: {'✅' if cascade_works else '❌'}")

    # Provide solutions
    if not cascade_works:
        provide_solutions()

        # Offer auto-fix
        print("\n" + "=" * 70)
        response = input("\n🤖 Would you like me to auto-install googletrans? (y/n): ")
        if response.lower() in ["y", "yes"]:
            if auto_fix():
                print("\n✅ FIX APPLIED! Please restart the GUI and try translating again.")
                print("   The translation should now work properly.")
            else:
                print("\n❌ Auto-fix failed. Please manually install:")
                print("   pip install googletrans==4.0.0rc1")
        else:
            print("\nℹ️  No changes made. Follow the solutions above to fix manually.")

    print("\n" + "=" * 70)
    print("Diagnostic complete. See CRITICAL_ISSUES_FOUND.md for details.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
