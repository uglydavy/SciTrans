"""Comprehensive test runner for translation pipeline quality validation."""

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, List

def validate_translation_output(input_pdf: str, output_pdf: str, artifacts_dir: str) -> Dict:
    """Validate translation output for quality issues."""
    results = {
        "pdf": input_pdf,
        "success": True,
        "errors": [],
        "warnings": [],
        "quality_scores": {},
    }
    
    # Check if output exists
    if not Path(output_pdf).exists():
        results["success"] = False
        results["errors"].append("Output PDF not created")
        return results
    
    # Load artifacts
    artifacts_path = Path(artifacts_dir)
    
    try:
        translations_data = json.loads((artifacts_path / "translations.json").read_text())
        
        # 1. Check for placeholder artifacts in output
        placeholder_pattern = r'<<[A-Z_]+_\d+>>'
        for tb in translations_data:
            translated_text = tb.get("translated_text", "")
            placeholders = re.findall(placeholder_pattern, translated_text)
            
            # Check if these are fake placeholders (not in source registry)
            source_text = tb.get("source_text", "")
            source_placeholders = re.findall(placeholder_pattern, source_text)
            
            fake_placeholders = set(placeholders) - set(source_placeholders)
            if fake_placeholders:
                results["errors"].append(
                    f"Block {tb['block_id']}: FAKE placeholders: {fake_placeholders}"
                )
                results["success"] = False
        
        # 2. Check for instruction spillover
        instruction_patterns = [
            r"n'oubliez pas", r"rappel\s*:", r"remarque\s*:",
            r"code erreur", r"formulaire", r"obligatoire",
            r"output only", r"remember:", r"critical:",
        ]
        for tb in translations_data:
            translated_text = tb.get("translated_text", "").lower()
            for pattern in instruction_patterns:
                if re.search(pattern, translated_text):
                    results["warnings"].append(
                        f"Block {tb['block_id']}: Possible instruction spillover: '{pattern}'"
                    )
        
        # 3. Check hallucination (extreme length ratio)
        for tb in translations_data:
            source_text = tb.get("source_text", "")
            translated_text = tb.get("translated_text", "")
            if source_text and translated_text:
                ratio = len(translated_text) / len(source_text)
                if ratio > 3.0:
                    results["warnings"].append(
                        f"Block {tb['block_id']}: Possible hallucination - {ratio:.1f}x longer"
                    )
        
        # 4. Load quality scores
        if (artifacts_path / "post_scores.json").exists():
            scores = json.loads((artifacts_path / "post_scores.json").read_text())
            if scores:
                avg_quality = sum(s.get("total_score", 0) for s in scores) / len(scores)
                results["quality_scores"]["average"] = avg_quality
                results["quality_scores"]["count"] = len(scores)
        
        # 5. Check block count
        parsed_data = json.loads((artifacts_path / "parsed.json").read_text())
        total_blocks = sum(len(p["blocks"]) for p in parsed_data["pages"])
        translated_count = len(translations_data)
        
        if translated_count < total_blocks:
            results["warnings"].append(
                f"Block count mismatch: {translated_count}/{total_blocks} translated"
            )
        
        results["quality_scores"]["blocks_translated"] = translated_count
        results["quality_scores"]["total_blocks"] = total_blocks
        results["quality_scores"]["coverage"] = (translated_count / total_blocks * 100) if total_blocks > 0 else 0
        
    except Exception as e:
        results["success"] = False
        results["errors"].append(f"Validation error: {e}")
    
    return results

def run_translation_test(input_pdf: str, backend: str = "cascade_free") -> Dict:
    """Run a single translation test and validate results."""
    pdf_name = Path(input_pdf).stem
    output_pdf = f"test_outputs/{pdf_name}_translated.pdf"
    artifacts_dir = f"outputs/{pdf_name}"
    
    # Clear previous artifacts
    if Path(artifacts_dir).exists():
        shutil.rmtree(artifacts_dir)
    
    print(f"\n{'='*60}")
    print(f"Testing: {input_pdf}")
    print(f"{'='*60}")
    
    # Run translation
    cmd = [
        ".venv/bin/scitrans", "translate",
        "--in", input_pdf,
        "--out", output_pdf,
        "--backend", backend,
        "--context", "3",
        "--n-candidates", "2",
    ]
    
    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            cwd="/Users/kv.kn/Desktop/Research/SciTrans_fixed",
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        elapsed = time.time() - start_time
        
        # Parse output for quality metrics
        output = result.stdout + result.stderr
        quality_match = re.search(r'Document Quality:\s*([\d.]+)%', output)
        confidence_match = re.search(r'Confidence:\s*([\d.]+)%', output)
        
        test_result = {
            "success": result.returncode == 0,
            "elapsed_time": elapsed,
            "quality": float(quality_match.group(1)) if quality_match else 0.0,
            "confidence": float(confidence_match.group(1)) if confidence_match else 0.0,
        }
        
        # Validate output
        validation = validate_translation_output(input_pdf, output_pdf, artifacts_dir)
        test_result.update(validation)
        
        # Print summary
        status = "✓ PASS" if test_result["success"] and not test_result["errors"] else "✗ FAIL"
        print(f"\n{status} - Quality: {test_result['quality']:.1f}% - Time: {elapsed:.1f}s")
        
        if test_result["errors"]:
            print(f"  Errors: {len(test_result['errors'])}")
            for error in test_result["errors"][:3]:
                print(f"    - {error}")
        
        if test_result["warnings"]:
            print(f"  Warnings: {len(test_result['warnings'])}")
            for warning in test_result["warnings"][:3]:
                print(f"    - {warning}")
        
        return test_result
        
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "errors": ["Translation timed out (>5min)"],
            "elapsed_time": 300,
            "quality": 0.0,
        }
    except Exception as e:
        return {
            "success": False,
            "errors": [f"Test failed: {e}"],
            "elapsed_time": 0,
            "quality": 0.0,
        }

def run_all_tests():
    """Run tests on all PDFs and generate comprehensive report."""
    os.makedirs("test_outputs", exist_ok=True)
    
    test_pdfs = [
        "test_pdfs/01_simple.pdf",
        "test_pdfs/02_medium_text.pdf",
        "test_pdfs/03_with_tables.pdf",
        "test_pdfs/04_with_math.pdf",
        "test_pdfs/05_with_lists.pdf",
        "test_pdfs/06_with_headers.pdf",
        "test_pdfs/07_multilingual.pdf",
        "test_pdfs/08_large_document.pdf",
        "test_pdfs/09_academic_paper.pdf",
        "test_pdfs/10_short_text.pdf",
    ]
    
    results = []
    for pdf in test_pdfs:
        if Path(pdf).exists():
            result = run_translation_test(pdf)
            results.append(result)
        else:
            print(f"⚠ Skipping {pdf} (not found)")
    
    # Generate report
    print(f"\n\n{'='*80}")
    print("COMPREHENSIVE TEST REPORT")
    print(f"{'='*80}\n")
    
    total_tests = len(results)
    passed_tests = sum(1 for r in results if r.get("success", False) and not r.get("errors"))
    avg_quality = sum(r.get("quality", 0) for r in results) / total_tests if total_tests > 0 else 0
    avg_time = sum(r.get("elapsed_time", 0) for r in results) / total_tests if total_tests > 0 else 0
    
    total_errors = sum(len(r.get("errors", [])) for r in results)
    total_warnings = sum(len(r.get("warnings", [])) for r in results)
    
    print(f"Tests Run:        {total_tests}")
    print(f"Tests Passed:     {passed_tests}/{total_tests} ({passed_tests/total_tests*100:.1f}%)")
    print(f"Average Quality:  {avg_quality:.1f}%")
    print(f"Average Time:     {avg_time:.1f}s")
    print(f"Total Errors:     {total_errors}")
    print(f"Total Warnings:   {total_warnings}")
    
    # Save detailed results
    report_file = "test_outputs/test_report.json"
    with open(report_file, 'w') as f:
        json.dump({
            "summary": {
                "total_tests": total_tests,
                "passed": passed_tests,
                "failed": total_tests - passed_tests,
                "pass_rate": passed_tests / total_tests if total_tests > 0 else 0,
                "avg_quality": avg_quality,
                "avg_time": avg_time,
                "total_errors": total_errors,
                "total_warnings": total_warnings,
            },
            "results": results
        }, f, indent=2)
    
    print(f"\n✓ Detailed report saved to: {report_file}")
    print(f"{'='*80}\n")
    
    return results

if __name__ == "__main__":
    run_all_tests()
