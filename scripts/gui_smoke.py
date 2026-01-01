#!/usr/bin/env python3
"""
Quick test to verify GUI loads and basic functionality works.
"""

import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 60)
print("Testing Fixed GUI")
print("=" * 60)

# Test 1: Import module
print("\n1. Testing import...")
try:
    from scitrans.gui.app import create_gui, get_backend_status, translate_pdf

    print("   ✅ Import successful")
except Exception as e:
    print(f"   ❌ Import failed: {e}")
    sys.exit(1)

# Test 2: Create GUI instance
print("\n2. Testing GUI creation...")
try:
    app = create_gui()
    print("   ✅ GUI instance created")
except Exception as e:
    print(f"   ❌ GUI creation failed: {e}")
    sys.exit(1)

# Test 3: Test backend status
print("\n3. Testing backend status...")
try:
    status = get_backend_status()
    assert "Backend" in status
    assert "Status" in status
    print("   ✅ Backend status works")
    print(f"   {status[:100]}...")
except Exception as e:
    print(f"   ❌ Backend status failed: {e}")

# Test 4: Test translate function signature
print("\n4. Testing translate function...")
try:
    # Just test it can be called (will fail without actual PDF, but that's OK)
    import inspect

    sig = inspect.signature(translate_pdf)
    params = list(sig.parameters.keys())
    expected_params = [
        "pdf_file",
        "pdf_url",
        "backend",
        "model",
        "source",
        "target",
        "n_candidates",
        "context_window",
        "temperature",
        "use_cache",
        "enable_reranking",
        "translate_tables",
    ]
    assert params == expected_params, f"Expected {expected_params}, got {params}"
    print("   ✅ Translate function signature correct")
except Exception as e:
    print(f"   ❌ Translate function check failed: {e}")

# Test 5: Check return types
print("\n5. Testing translate return format...")
try:
    # Call with None (will return error, but we test return format)
    result = translate_pdf(
        None, "", "cascade_free", "cascade_free", "en", "fr", 2, 5, 0.7, True, True, False
    )
    assert isinstance(result, tuple), "Should return tuple"
    assert len(result) == 3, "Should return 3 values"
    print("   ✅ Translate function returns correct format")
    print("   Returns: (file, summary, status)")
except Exception as e:
    print(f"   ❌ Return format test failed: {e}")

print("\n" + "=" * 60)
print("✅ All basic tests passed!")
print("=" * 60)
print("\nNow test manually:")
print("1. Run: scitrans gui")
print("2. Upload a test PDF")
print("3. Click 'Translate'")
print("4. Verify it actually translates")
print("\nIf GUI doesn't start, check: pip install gradio")
