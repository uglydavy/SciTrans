#!/bin/bash
# Install backend dependencies and test translation

set -e

echo "🔧 Installing Backend Dependencies"
echo "===================================="

cd "$(dirname "$0")/.."

# Install backend SDKs
echo "Installing backend SDKs..."
pip install openai>=1.0.0 anthropic>=0.34.0 googletrans==4.0.0rc1 requests>=2.31.0

echo ""
echo "✅ Dependencies installed!"
echo ""

# Load environment variables
echo "📋 Loading environment variables..."
if [ -f "setup_env.sh" ]; then
    source setup_env.sh
    echo "✅ Environment variables loaded"
else
    echo "❌ setup_env.sh not found!"
    exit 1
fi

echo ""
echo "🧪 Testing Backends"
echo "===================================="

# Test each backend
python3 << 'EOF'
import os
import sys

print("\n1. Testing DeepSeek Backend:")
try:
    from scitrans.translation.backends.deepseek_backend import DeepSeekBackend
    from scitrans.translation.backends.base import TranslateRequest
    
    backend = DeepSeekBackend()
    req = TranslateRequest(
        text="Hello world, this is a test.",
        source_lang="en",
        target_lang="fr",
        system_prompt="Translate to French"
    )
    result = backend.translate(req)
    
    print(f"   Input:  '{req.text}'")
    print(f"   Output: '{result.candidates[0]}'")
    
    if result.candidates[0] != req.text:
        print(f"   ✅ DeepSeek WORKS! Translation successful!")
    else:
        print(f"   ❌ DeepSeek returned same text (no translation)")
        sys.exit(1)
except Exception as e:
    print(f"   ❌ DeepSeek failed: {str(e)[:200]}")
    sys.exit(1)

print("\n2. Testing OpenAI Backend:")
try:
    from scitrans.translation.backends.openai_backend import OpenAIBackend
    from scitrans.translation.backends.base import TranslateRequest
    
    backend = OpenAIBackend()
    req = TranslateRequest(
        text="Hello world, this is a test.",
        source_lang="en",
        target_lang="fr",
        system_prompt="Translate to French"
    )
    result = backend.translate(req)
    
    print(f"   Input:  '{req.text}'")
    print(f"   Output: '{result.candidates[0]}'")
    
    if result.candidates[0] != req.text:
        print(f"   ✅ OpenAI WORKS! Translation successful!")
    else:
        print(f"   ❌ OpenAI returned same text")
        sys.exit(1)
except Exception as e:
    print(f"   ❌ OpenAI failed: {str(e)[:200]}")
    # Don't exit - OpenAI might not be configured

print("\n3. Testing Google Translate:")
try:
    from scitrans.translation.backends.google_backend import GoogleTranslateBackend
    from scitrans.translation.backends.base import TranslateRequest
    
    backend = GoogleTranslateBackend()
    req = TranslateRequest(
        text="Hello world, this is a test.",
        source_lang="en",
        target_lang="fr",
        system_prompt="Translate to French"
    )
    result = backend.translate(req)
    
    print(f"   Input:  '{req.text}'")
    print(f"   Output: '{result.candidates[0]}'")
    
    if result.candidates[0] != req.text:
        print(f"   ✅ Google Translate WORKS!")
    else:
        print(f"   ❌ Google returned same text")
except Exception as e:
    print(f"   ⚠️  Google Translate: {str(e)[:200]}")

print("\n4. Testing cascade_free:")
try:
    from scitrans.translation.backends.cascade_free import CascadeFreeBackend
    from scitrans.translation.backends.base import TranslateRequest
    
    backend = CascadeFreeBackend()
    print(f"   ✅ cascade_free initialized with {len(backend._backends)} backends:")
    for name, _ in backend._backends:
        print(f"      • {name}")
    
    req = TranslateRequest(
        text="Hello world, this is a test.",
        source_lang="en",
        target_lang="fr",
        system_prompt="Translate to French"
    )
    result = backend.translate(req)
    
    print(f"   Input:  '{req.text}'")
    print(f"   Output: '{result.candidates[0]}'")
    
    if result.candidates[0] != req.text:
        print(f"   ✅ cascade_free WORKS!")
    else:
        print(f"   ❌ cascade_free returned same text")
except Exception as e:
    print(f"   ❌ cascade_free failed: {str(e)[:300]}")

print("\n" + "=" * 60)
print("✅ Backend testing complete!")
print("=" * 60)
EOF

echo ""
echo "🎉 Setup Complete!"
echo ""
echo "Next steps:"
echo "1. Launch GUI: scitrans gui"
echo "2. Or test CLI: scitrans translate --in test.pdf --out test_fr.pdf --backend deepseek"

