#!/usr/bin/env python3
"""
Quick verification script to check medium_test.pdf translation results.
Can be run independently after translation completes.
"""

import json
import sys
from pathlib import Path


def verify_results(artifacts_dir: str = "outputs/medium_test/medium_test") -> tuple[bool, dict]:
    """Verify translation results and return (success, details)."""
    artifacts_path = Path(artifacts_dir)
    
    # Load report.json
    report_path = artifacts_path / "report.json"
    if not report_path.exists():
        return False, {"error": f"report.json not found at {report_path}"}
    
    report = json.loads(report_path.read_text(encoding="utf-8"))
    
    # Load translations.json
    translations_path = artifacts_path / "translations.json"
    translations = []
    if translations_path.exists():
        translations = json.loads(translations_path.read_text(encoding="utf-8"))
    
    # Extract metrics
    num_blocks = report.get("num_blocks", 0)
    num_ok = report.get("num_ok", 0)
    num_failed = report.get("num_failed", 0)
    scoring = report.get("scoring", {})
    document_quality = scoring.get("document_quality", 0.0)
    
    # Count emergency translations and fallbacks
    emergency_count = sum(1 for tb in translations if tb.get("meta", {}).get("emergency_translation"))
    fallback_count = sum(1 for tb in translations if tb.get("meta", {}).get("used_source_text"))
    
    # Verify criteria
    criteria = {
        "all_blocks_translated": num_ok == num_blocks,
        "quality_above_90": document_quality >= 0.90,
        "zero_failed": num_failed == 0,
        "emergency_under_3": emergency_count < 3,
        "zero_fallbacks": fallback_count == 0,
    }
    
    all_passed = all(criteria.values())
    
    details = {
        "num_blocks": num_blocks,
        "num_ok": num_ok,
        "num_failed": num_failed,
        "document_quality": document_quality,
        "emergency_count": emergency_count,
        "fallback_count": fallback_count,
        "criteria": criteria,
        "all_passed": all_passed,
    }
    
    return all_passed, details


def main():
    """Main function."""
    from pathlib import Path
    
    # Try multiple possible locations for report.json
    possible_dirs = [
        sys.argv[1] if len(sys.argv) > 1 else None,
        "outputs/medium_test/medium_test",
        "outputs/medium_test",
    ]
    
    artifacts_dir = None
    for dir_path in possible_dirs:
        if dir_path and Path(dir_path).exists() and (Path(dir_path) / "report.json").exists():
            artifacts_dir = dir_path
            break
    
    if not artifacts_dir:
        # Try to find it automatically
        report_files = list(Path("outputs").rglob("report.json"))
        medium_reports = [f.parent for f in report_files if "medium_test" in str(f).lower()]
        if medium_reports:
            artifacts_dir = str(medium_reports[0])
        else:
            artifacts_dir = "outputs/medium_test/medium_test"  # Default
    
    print(f"\n{'='*60}")
    print("VERIFYING MEDIUM_TEST.PDF TRANSLATION RESULTS")
    print(f"{'='*60}\n")
    
    success, details = verify_results(artifacts_dir)
    
    if "error" in details:
        print(f"❌ {details['error']}")
        sys.exit(1)
    
    print(f"Total blocks: {details['num_blocks']}")
    print(f"Successful: {details['num_ok']}")
    print(f"Failed: {details['num_failed']}")
    print(f"Document Quality: {details['document_quality']:.1%}")
    print(f"Emergency translations: {details['emergency_count']}")
    print(f"Source text fallbacks: {details['fallback_count']}")
    print()
    
    print("Success Criteria:")
    criteria = details['criteria']
    print(f"  ✅ All blocks translated: {criteria['all_blocks_translated']}")
    print(f"  ✅ Quality > 90%: {criteria['quality_above_90']} ({details['document_quality']:.1%})")
    print(f"  ✅ Zero failed blocks: {criteria['zero_failed']}")
    print(f"  ✅ Emergency < 3: {criteria['emergency_under_3']} ({details['emergency_count']})")
    print(f"  ✅ Zero fallbacks: {criteria['zero_fallbacks']} ({details['fallback_count']})")
    print()
    
    if success:
        print("🎉 ALL SUCCESS CRITERIA MET!")
        print("✅ Test PASSED - 100% success rate achieved!")
        sys.exit(0)
    else:
        print("❌ SOME SUCCESS CRITERIA FAILED")
        failed = [k for k, v in criteria.items() if not v]
        for f in failed:
            print(f"  ❌ {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
