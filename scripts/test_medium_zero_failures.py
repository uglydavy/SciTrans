#!/usr/bin/env python3
"""
Test script to verify 100% success rate (0 failures) for medium_test.pdf translation.

Success Criteria:
- ✅ All blocks translated (num_ok == num_blocks)
- ✅ Quality > 90%
- ✅ Zero failed blocks (num_failed == 0)
- ✅ < 3 emergency translations
- ✅ Zero source text fallbacks
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any


def run_translation() -> tuple[bool, str, Dict[str, Any]]:
    """Run translation command and return success status, output, and report."""
    input_pdf = "test_pdfs/medium_test.pdf"
    output_pdf = "test_outputs/test_zero_failures_medium.pdf"
    artifacts_dir = "outputs/medium_test"
    
    # Ensure output directory exists
    Path("test_outputs").mkdir(exist_ok=True)
    
    # Use venv Python if available, otherwise system python3
    import sys
    venv_python = Path(".venv/bin/python3")
    if venv_python.exists():
        python_cmd = str(venv_python.absolute())
    else:
        python_cmd = sys.executable
    
    cmd = [
        python_cmd, "-m", "scitrans.cli.main", "translate",
        "--in", input_pdf,
        "--out", output_pdf,
        "--source", "en",
        "--target", "fr",
        "--backend", "cascade_free",
        "--artifacts", artifacts_dir,
    ]
    
    print(f"\n{'='*60}")
    print("Running translation test for medium_test.pdf")
    print(f"{'='*60}")
    print(f"Command: {' '.join(cmd)}")
    print()
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800  # 30 minute timeout for medium PDF
        )
        
        stdout = result.stdout
        stderr = result.stderr
        
        # Load report.json - pipeline creates nested directory: artifacts_dir / pdf_stem / report.json
        # For medium_test.pdf, the report is at outputs/medium_test/medium_test/report.json
        pdf_stem = Path(input_pdf).stem
        report_path = Path(artifacts_dir) / pdf_stem / "report.json"
        if not report_path.exists():
            # Try direct path as fallback
            report_path = Path(artifacts_dir) / "report.json"
        
        if report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8"))
        else:
            report = {}
        
        return result.returncode == 0, stdout + stderr, report
    except subprocess.TimeoutExpired:
        return False, "Translation timed out after 10 minutes", {}
    except Exception as e:
        return False, f"Error running translation: {e}", {}


def load_translations(artifacts_dir: str) -> list[Dict[str, Any]]:
    """Load translations.json to check for emergency translations and fallbacks."""
    # artifacts_dir might be the full path or just the base directory
    translations_path = Path(artifacts_dir) / "translations.json"
    if not translations_path.exists():
        # Try nested structure: artifacts_dir / pdf_stem / translations.json
        # This handles case where artifacts_dir is just "outputs/medium_test"
        pdf_stem = "medium_test"  # From test_pdfs/medium_test.pdf
        translations_path = Path(artifacts_dir) / pdf_stem / "translations.json"
    
    if translations_path.exists():
        return json.loads(translations_path.read_text(encoding="utf-8"))
    return []


def count_emergency_and_fallbacks(translations: list[Dict[str, Any]]) -> tuple[int, int]:
    """Count emergency translations and source text fallbacks from translations.json."""
    emergency_count = 0
    fallback_count = 0
    
    # translations.json contains list of TranslatedBlock objects (from model_dump())
    for tb in translations:
        meta = tb.get("meta", {})
        if meta.get("emergency_translation"):
            emergency_count += 1
        if meta.get("used_source_text"):
            fallback_count += 1
    
    return emergency_count, fallback_count


def verify_success_criteria(report: Dict[str, Any], artifacts_dir: str) -> tuple[bool, list[str]]:
    """Verify all success criteria and return (success, list of failures)."""
    failures = []
    
    # Extract metrics from report
    num_blocks = report.get("num_blocks", 0)
    num_ok = report.get("num_ok", 0)
    num_failed = report.get("num_failed", 0)
    scoring = report.get("scoring", {})
    document_quality = scoring.get("document_quality", 0.0)
    
    # Check translations.json for emergency/fallback metadata
    translations = load_translations(artifacts_dir)
    emergency_count, fallback_count = count_emergency_and_fallbacks(translations)
    
    print(f"\n{'='*60}")
    print("VERIFICATION RESULTS")
    print(f"{'='*60}")
    
    # Criterion 1: All blocks translated
    if num_ok == num_blocks:
        print(f"✅ All {num_blocks} blocks translated successfully")
    else:
        failures.append(f"❌ Only {num_ok}/{num_blocks} blocks translated (expected {num_blocks}/{num_blocks})")
        print(failures[-1])
    
    # Criterion 2: Quality > 90%
    if document_quality >= 0.90:
        print(f"✅ Document quality: {document_quality:.1%} (target: >90%)")
    else:
        failures.append(f"❌ Document quality: {document_quality:.1%} (target: >90%)")
        print(failures[-1])
    
    # Criterion 3: Zero failed blocks
    if num_failed == 0:
        print(f"✅ Zero failed blocks: {num_failed}")
    else:
        failures.append(f"❌ Failed blocks: {num_failed} (expected 0)")
        print(failures[-1])
    
    # Criterion 4: < 3 emergency translations
    if emergency_count < 3:
        print(f"✅ Emergency translations: {emergency_count} (target: <3)")
    else:
        failures.append(f"❌ Emergency translations: {emergency_count} (target: <3)")
        print(failures[-1])
    
    # Criterion 5: Zero source text fallbacks
    if fallback_count == 0:
        print(f"✅ Source text fallbacks: {fallback_count} (target: 0)")
    else:
        failures.append(f"❌ Source text fallbacks: {fallback_count} (target: 0)")
        print(failures[-1])
    
    print(f"{'='*60}\n")
    
    return len(failures) == 0, failures


def main():
    """Main test function."""
    # Run translation
    success, output, report = run_translation()
    
    if not success:
        print("❌ Translation command failed!")
        print("\nOutput:")
        print(output)
        sys.exit(1)
    
    # Extract artifacts directory from report
    # The report contains the full path, but we need to use it correctly
    artifacts_dir_from_report = report.get("artifacts_dir", "")
    if artifacts_dir_from_report:
        # Report contains full path like "outputs/medium_test/medium_test"
        artifacts_dir = artifacts_dir_from_report
    else:
        # Fallback: construct from input PDF name
        artifacts_dir = "outputs/medium_test/medium_test"
    
    # Verify success criteria
    all_passed, failures = verify_success_criteria(report, artifacts_dir)
    
    # Print detailed report
    print("\n" + "="*60)
    print("DETAILED REPORT")
    print("="*60)
    print(f"Total blocks: {report.get('num_blocks', 0)}")
    print(f"Successful: {report.get('num_ok', 0)}")
    print(f"Failed: {report.get('num_failed', 0)}")
    
    scoring = report.get("scoring", {})
    print(f"Document Quality: {scoring.get('document_quality', 0):.1%}")
    print(f"Confidence: {scoring.get('document_confidence', 0):.1%}")
    print(f"Acceptance Rate: {scoring.get('acceptance_rate', 0):.1%}")
    print(f"Elapsed Time: {report.get('elapsed_s', 0):.1f}s")
    
    # Load and display emergency/fallback counts
    translations = load_translations(artifacts_dir)
    emergency_count, fallback_count = count_emergency_and_fallbacks(translations)
    print(f"Emergency translations: {emergency_count}")
    print(f"Source text fallbacks: {fallback_count}")
    print("="*60)
    
    # Final result
    if all_passed:
        print("\n🎉 ALL SUCCESS CRITERIA MET!")
        print("✅ Test PASSED - 100% success rate achieved!")
        sys.exit(0)
    else:
        print("\n❌ SOME SUCCESS CRITERIA FAILED:")
        for failure in failures:
            print(f"  {failure}")
        sys.exit(1)


if __name__ == "__main__":
    main()
