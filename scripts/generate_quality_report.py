#!/usr/bin/env python3
"""Generate comprehensive quality report with before/after comparisons.

This script analyzes all translation test outputs and generates:
1. Before/After metrics comparison
2. Quality score analysis
3. Issue detection and categorization
4. Performance benchmarks
5. HTML and JSON reports
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def load_json(path: Path) -> Optional[Union[Dict[str, Any], List[Any]]]:
    """Load JSON file safely."""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  Warning: Could not load {path}: {e}")
        return None


def analyze_test_case(output_dir: Path) -> Dict[str, Any]:
    """Analyze a single test case output directory."""
    result = {
        "test_name": output_dir.name,
        "has_output": False,
        "before": {},
        "after": {},
        "issues": [],
        "warnings": [],
        "metrics": {}
    }
    
    # Load all available JSON files
    report = load_json(output_dir / "report.json")
    pre_scores = load_json(output_dir / "pre_scores.json")
    post_scores = load_json(output_dir / "post_scores.json")
    health_scores = load_json(output_dir / "health_scores.json")
    masked = load_json(output_dir / "masked.json")
    
    if not report:
        return result
    
    result["has_output"] = True
    
    # === BEFORE (Pre-translation) Metrics ===
    if pre_scores:
        pre_metrics = {
            "total_blocks": len(pre_scores),
            "avg_complexity": sum(s.get("complexity_score", 0) for s in pre_scores) / len(pre_scores),
            "complex_blocks": sum(1 for s in pre_scores if s.get("complexity_score", 0) > 0.6),
            "has_math": sum(1 for s in pre_scores if s.get("has_math", False)),
            "has_tables": sum(1 for s in pre_scores if s.get("has_tables", False)),
            "has_code": sum(1 for s in pre_scores if s.get("has_code", False)),
            "has_citations": sum(1 for s in pre_scores if s.get("has_citations", False)),
            "has_bullets": sum(1 for s in pre_scores if s.get("has_bullets", False)),
            "avg_word_count": sum(s.get("word_count", 0) for s in pre_scores) / len(pre_scores),
            "total_words": sum(s.get("word_count", 0) for s in pre_scores),
        }
        result["before"] = pre_metrics
    
    # === AFTER (Post-translation) Metrics ===
    if post_scores:
        post_metrics = {
            "blocks_scored": len(post_scores),
            "avg_overall_score": sum(s.get("overall_score", 0) for s in post_scores) / len(post_scores),
            "avg_placeholder_score": sum(s.get("placeholder_score", 0) for s in post_scores) / len(post_scores),
            "avg_numeric_score": sum(s.get("numeric_score", 0) for s in post_scores) / len(post_scores),
            "avg_format_score": sum(s.get("format_score", 0) for s in post_scores) / len(post_scores),
            "avg_fluency_score": sum(s.get("fluency_score", 0) for s in post_scores) / len(post_scores),
            "avg_fidelity_score": sum(s.get("fidelity_score", 0) for s in post_scores) / len(post_scores),
            "blocks_need_review": sum(1 for s in post_scores if s.get("needs_review", False)),
            "blocks_need_retry": sum(1 for s in post_scores if s.get("needs_retry", False)),
            "total_issues": sum(len(s.get("issues", [])) for s in post_scores),
            "total_warnings": sum(len(s.get("warnings", [])) for s in post_scores),
        }
        result["after"] = post_metrics
        
        # Collect all issues and warnings
        for score in post_scores:
            result["issues"].extend(score.get("issues", []))
            result["warnings"].extend(score.get("warnings", []))
    
    # === Health Metrics ===
    if health_scores:
        health_metrics = {
            "ok_blocks": sum(1 for h in health_scores if h.get("status") == "ok"),
            "warning_blocks": sum(1 for h in health_scores if h.get("status") == "warning"),
            "failed_blocks": sum(1 for h in health_scores if h.get("status") == "failed"),
            "avg_health_score": sum(h.get("score", 0) for h in health_scores) / len(health_scores),
        }
        result["metrics"]["health"] = health_metrics
    
    # === Overall Metrics from Report ===
    if report:
        result["metrics"]["overall"] = {
            "document_quality": report.get("scoring", {}).get("document_quality", 0),
            "document_confidence": report.get("scoring", {}).get("document_confidence", 0),
            "blocks_total": report.get("num_blocks", 0),
            "blocks_ok": report.get("num_ok", 0),
            "blocks_failed": report.get("num_failed", 0),
            "elapsed_seconds": report.get("elapsed_s", 0),
            "backend": report.get("backend", "unknown"),
        }
    
    # === Masking Analysis ===
    if masked and isinstance(masked, list):
        total_placeholders = 0
        placeholder_types = {}
        
        for block in masked:
            mask_counts = block.get("mask_counts", {})
            for mask_type, count in mask_counts.items():
                total_placeholders += count
                placeholder_types[mask_type] = placeholder_types.get(mask_type, 0) + count
        
        result["metrics"]["masking"] = {
            "total_placeholders": total_placeholders,
            "placeholder_types": placeholder_types,
        }
    
    return result


def generate_summary_stats(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate overall summary statistics."""
    valid_results = [r for r in results if r["has_output"]]
    
    if not valid_results:
        return {"error": "No valid results found"}
    
    summary = {
        "total_tests": len(results),
        "successful_tests": len(valid_results),
        "failed_tests": len(results) - len(valid_results),
        "timestamp": datetime.now().isoformat(),
    }
    
    # Aggregate before metrics
    if any(r.get("before") for r in valid_results):
        summary["before_aggregate"] = {
            "total_blocks": sum(r["before"].get("total_blocks", 0) for r in valid_results if "before" in r),
            "total_words": sum(r["before"].get("total_words", 0) for r in valid_results if "before" in r),
            "avg_complexity": sum(r["before"].get("avg_complexity", 0) for r in valid_results if "before" in r) / len(valid_results),
            "total_complex_blocks": sum(r["before"].get("complex_blocks", 0) for r in valid_results if "before" in r),
            "total_math_blocks": sum(r["before"].get("has_math", 0) for r in valid_results if "before" in r),
            "total_table_blocks": sum(r["before"].get("has_tables", 0) for r in valid_results if "before" in r),
            "total_code_blocks": sum(r["before"].get("has_code", 0) for r in valid_results if "before" in r),
        }
    
    # Aggregate after metrics
    if any(r.get("after") for r in valid_results):
        valid_after = [r for r in valid_results if "after" in r and r["after"]]
        if valid_after:
            summary["after_aggregate"] = {
                "avg_overall_score": sum(r["after"].get("avg_overall_score", 0) for r in valid_after) / len(valid_after),
                "avg_placeholder_score": sum(r["after"].get("avg_placeholder_score", 0) for r in valid_after) / len(valid_after),
                "avg_numeric_score": sum(r["after"].get("avg_numeric_score", 0) for r in valid_after) / len(valid_after),
                "avg_format_score": sum(r["after"].get("avg_format_score", 0) for r in valid_after) / len(valid_after),
                "avg_fluency_score": sum(r["after"].get("avg_fluency_score", 0) for r in valid_after) / len(valid_after),
                "avg_fidelity_score": sum(r["after"].get("avg_fidelity_score", 0) for r in valid_after) / len(valid_after),
                "total_issues": sum(r["after"].get("total_issues", 0) for r in valid_after),
                "total_warnings": sum(r["after"].get("total_warnings", 0) for r in valid_after),
                "blocks_need_review": sum(r["after"].get("blocks_need_review", 0) for r in valid_after),
                "blocks_need_retry": sum(r["after"].get("blocks_need_retry", 0) for r in valid_after),
            }
    
    # Aggregate health metrics
    valid_health = [r for r in valid_results if "health" in r.get("metrics", {})]
    if valid_health:
        summary["health_aggregate"] = {
            "total_ok_blocks": sum(r["metrics"]["health"].get("ok_blocks", 0) for r in valid_health),
            "total_warning_blocks": sum(r["metrics"]["health"].get("warning_blocks", 0) for r in valid_health),
            "total_failed_blocks": sum(r["metrics"]["health"].get("failed_blocks", 0) for r in valid_health),
            "avg_health_score": sum(r["metrics"]["health"].get("avg_health_score", 0) for r in valid_health) / len(valid_health),
        }
    
    # Overall quality metrics
    valid_overall = [r for r in valid_results if "overall" in r.get("metrics", {})]
    if valid_overall:
        summary["overall_aggregate"] = {
            "avg_document_quality": sum(r["metrics"]["overall"].get("document_quality", 0) for r in valid_overall) / len(valid_overall),
            "avg_document_confidence": sum(r["metrics"]["overall"].get("document_confidence", 0) for r in valid_overall) / len(valid_overall),
            "total_blocks": sum(r["metrics"]["overall"].get("blocks_total", 0) for r in valid_overall),
            "total_blocks_ok": sum(r["metrics"]["overall"].get("blocks_ok", 0) for r in valid_overall),
            "total_blocks_failed": sum(r["metrics"]["overall"].get("blocks_failed", 0) for r in valid_overall),
            "total_elapsed_seconds": sum(r["metrics"]["overall"].get("elapsed_seconds", 0) for r in valid_overall),
        }
        
        # Calculate success rate
        total = summary["overall_aggregate"]["total_blocks"]
        ok = summary["overall_aggregate"]["total_blocks_ok"]
        summary["overall_aggregate"]["block_success_rate"] = ok / total if total > 0 else 0
    
    # Collect all unique issues and warnings
    all_issues = []
    all_warnings = []
    for r in valid_results:
        all_issues.extend(r.get("issues", []))
        all_warnings.extend(r.get("warnings", []))
    
    summary["issue_breakdown"] = categorize_issues(all_issues)
    summary["warning_breakdown"] = categorize_issues(all_warnings)
    
    return summary


def categorize_issues(items: List[str]) -> Dict[str, int]:
    """Categorize issues/warnings by type."""
    categories = {}
    for item in items:
        # Extract category from issue string (e.g., "placeholder_leak:...")
        category = item.split(":")[0] if ":" in item else item
        categories[category] = categories.get(category, 0) + 1
    return dict(sorted(categories.items(), key=lambda x: x[1], reverse=True))


def print_colored_report(summary: Dict[str, Any], results: List[Dict[str, Any]]):
    """Print a colored terminal report."""
    print(f"\n{Colors.HEADER}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}📊 SCITRANS QUALITY REPORT - BEFORE/AFTER COMPARISON{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*80}{Colors.ENDC}\n")
    
    print(f"Generated: {summary.get('timestamp', 'N/A')}")
    print(f"Total Tests: {summary['total_tests']}")
    print(f"✅ Successful: {summary['successful_tests']}")
    print(f"❌ Failed: {summary['failed_tests']}\n")
    
    # === BEFORE (Pre-Translation) Summary ===
    if "before_aggregate" in summary:
        print(f"{Colors.OKBLUE}{Colors.BOLD}📋 BEFORE TRANSLATION (Source Analysis){Colors.ENDC}")
        print(f"{Colors.OKBLUE}{'─'*80}{Colors.ENDC}")
        before = summary["before_aggregate"]
        print(f"  Total Blocks Analyzed:  {before['total_blocks']}")
        print(f"  Total Words:            {before['total_words']}")
        print(f"  Avg Complexity:         {before['avg_complexity']:.3f}")
        print(f"  Complex Blocks:         {before['total_complex_blocks']}")
        print(f"  Math Blocks:            {before['total_math_blocks']}")
        print(f"  Table Blocks:           {before['total_table_blocks']}")
        print(f"  Code Blocks:            {before['total_code_blocks']}")
        print()
    
    # === AFTER (Post-Translation) Summary ===
    if "after_aggregate" in summary:
        print(f"{Colors.OKGREEN}{Colors.BOLD}✨ AFTER TRANSLATION (Quality Analysis){Colors.ENDC}")
        print(f"{Colors.OKGREEN}{'─'*80}{Colors.ENDC}")
        after = summary["after_aggregate"]
        
        # Format scores with color
        def score_color(score: float) -> str:
            if score >= 0.9:
                return Colors.OKGREEN
            elif score >= 0.7:
                return Colors.WARNING
            else:
                return Colors.FAIL
        
        overall = after['avg_overall_score']
        placeholder = after['avg_placeholder_score']
        numeric = after['avg_numeric_score']
        format_score = after['avg_format_score']
        fluency = after['avg_fluency_score']
        fidelity = after['avg_fidelity_score']
        
        print(f"  Overall Score:          {score_color(overall)}{overall:.3f}{Colors.ENDC}")
        print(f"  Placeholder Score:      {score_color(placeholder)}{placeholder:.3f}{Colors.ENDC}")
        print(f"  Numeric Score:          {score_color(numeric)}{numeric:.3f}{Colors.ENDC}")
        print(f"  Format Score:           {score_color(format_score)}{format_score:.3f}{Colors.ENDC}")
        print(f"  Fluency Score:          {score_color(fluency)}{fluency:.3f}{Colors.ENDC}")
        print(f"  Fidelity Score:         {score_color(fidelity)}{fidelity:.3f}{Colors.ENDC}")
        print()
        print(f"  Blocks Need Review:     {after['blocks_need_review']}")
        print(f"  Blocks Need Retry:      {after['blocks_need_retry']}")
        print(f"  Total Issues:           {Colors.FAIL}{after['total_issues']}{Colors.ENDC}")
        print(f"  Total Warnings:         {Colors.WARNING}{after['total_warnings']}{Colors.ENDC}")
        print()
    
    # === Health Summary ===
    if "health_aggregate" in summary:
        print(f"{Colors.OKCYAN}{Colors.BOLD}🏥 HEALTH METRICS{Colors.ENDC}")
        print(f"{Colors.OKCYAN}{'─'*80}{Colors.ENDC}")
        health = summary["health_aggregate"]
        print(f"  OK Blocks:              {Colors.OKGREEN}{health['total_ok_blocks']}{Colors.ENDC}")
        print(f"  Warning Blocks:         {Colors.WARNING}{health['total_warning_blocks']}{Colors.ENDC}")
        print(f"  Failed Blocks:          {Colors.FAIL}{health['total_failed_blocks']}{Colors.ENDC}")
        print(f"  Avg Health Score:       {health['avg_health_score']:.3f}")
        print()
    
    # === Overall Performance ===
    if "overall_aggregate" in summary:
        print(f"{Colors.BOLD}⚡ OVERALL PERFORMANCE{Colors.ENDC}")
        print(f"{'─'*80}")
        overall = summary["overall_aggregate"]
        quality = overall['avg_document_quality']
        confidence = overall['avg_document_confidence']
        success_rate = overall['block_success_rate']
        
        print(f"  Document Quality:       {score_color(quality)}{quality:.1%}{Colors.ENDC}")
        print(f"  Document Confidence:    {score_color(confidence)}{confidence:.1%}{Colors.ENDC}")
        print(f"  Block Success Rate:     {score_color(success_rate)}{success_rate:.1%}{Colors.ENDC}")
        print(f"  Total Processing Time:  {overall['total_elapsed_seconds']:.1f}s")
        print(f"  Avg Time per Document:  {overall['total_elapsed_seconds'] / summary['successful_tests']:.1f}s")
        print()
    
    # === Issue Breakdown ===
    if summary.get("issue_breakdown"):
        print(f"{Colors.FAIL}{Colors.BOLD}⚠️  ISSUE BREAKDOWN{Colors.ENDC}")
        print(f"{Colors.FAIL}{'─'*80}{Colors.ENDC}")
        for issue_type, count in list(summary["issue_breakdown"].items())[:10]:
            print(f"  {issue_type:40s} {count:3d}")
        if len(summary["issue_breakdown"]) > 10:
            print(f"  ... and {len(summary['issue_breakdown']) - 10} more")
        print()
    
    # === Warning Breakdown ===
    if summary.get("warning_breakdown"):
        print(f"{Colors.WARNING}{Colors.BOLD}⚡ WARNING BREAKDOWN{Colors.ENDC}")
        print(f"{Colors.WARNING}{'─'*80}{Colors.ENDC}")
        for warning_type, count in list(summary["warning_breakdown"].items())[:10]:
            print(f"  {warning_type:40s} {count:3d}")
        if len(summary["warning_breakdown"]) > 10:
            print(f"  ... and {len(summary['warning_breakdown']) - 10} more")
        print()
    
    # === Per-Test Results ===
    print(f"{Colors.BOLD}📑 PER-TEST RESULTS{Colors.ENDC}")
    print(f"{'─'*80}")
    
    valid_results = [r for r in results if r["has_output"]]
    for r in valid_results:
        test_name = r["test_name"]
        quality = r.get("metrics", {}).get("overall", {}).get("document_quality", 0)
        confidence = r.get("metrics", {}).get("overall", {}).get("document_confidence", 0)
        
        # Determine status
        if quality >= 0.9 and confidence >= 0.9:
            status = f"{Colors.OKGREEN}✅ EXCELLENT{Colors.ENDC}"
        elif quality >= 0.7 and confidence >= 0.7:
            status = f"{Colors.WARNING}⚠️  GOOD{Colors.ENDC}"
        else:
            status = f"{Colors.FAIL}❌ NEEDS WORK{Colors.ENDC}"
        
        print(f"  {test_name:30s} Quality: {quality:.1%} | Confidence: {confidence:.1%} | {status}")
    
    print(f"\n{Colors.HEADER}{'='*80}{Colors.ENDC}\n")


def generate_html_report(summary: Dict[str, Any], results: List[Dict[str, Any]], output_path: Path):
    """Generate HTML report."""
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>SciTrans Quality Report</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 20px;
            background: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 30px;
            border-left: 4px solid #3498db;
            padding-left: 10px;
        }}
        .metric-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .metric-card {{
            background: #ecf0f1;
            padding: 15px;
            border-radius: 6px;
            border-left: 4px solid #3498db;
        }}
        .metric-card h3 {{
            margin: 0 0 10px 0;
            color: #2c3e50;
            font-size: 14px;
            text-transform: uppercase;
        }}
        .metric-value {{
            font-size: 24px;
            font-weight: bold;
            color: #2c3e50;
        }}
        .score-excellent {{ color: #27ae60; }}
        .score-good {{ color: #f39c12; }}
        .score-poor {{ color: #e74c3c; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background: #34495e;
            color: white;
        }}
        tr:hover {{
            background: #f5f5f5;
        }}
        .timestamp {{
            color: #7f8c8d;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 SciTrans Quality Report</h1>
        <p class="timestamp">Generated: {summary.get('timestamp', 'N/A')}</p>
        
        <h2>Summary</h2>
        <div class="metric-grid">
            <div class="metric-card">
                <h3>Total Tests</h3>
                <div class="metric-value">{summary['total_tests']}</div>
            </div>
            <div class="metric-card">
                <h3>Successful</h3>
                <div class="metric-value score-excellent">{summary['successful_tests']}</div>
            </div>
            <div class="metric-card">
                <h3>Failed</h3>
                <div class="metric-value score-poor">{summary['failed_tests']}</div>
            </div>
        </div>
"""
    
    # Add before metrics
    if "before_aggregate" in summary:
        before = summary["before_aggregate"]
        html += f"""
        <h2>📋 Before Translation (Source Analysis)</h2>
        <div class="metric-grid">
            <div class="metric-card">
                <h3>Total Blocks</h3>
                <div class="metric-value">{before['total_blocks']}</div>
            </div>
            <div class="metric-card">
                <h3>Total Words</h3>
                <div class="metric-value">{before['total_words']}</div>
            </div>
            <div class="metric-card">
                <h3>Avg Complexity</h3>
                <div class="metric-value">{before['avg_complexity']:.3f}</div>
            </div>
            <div class="metric-card">
                <h3>Complex Blocks</h3>
                <div class="metric-value">{before['total_complex_blocks']}</div>
            </div>
            <div class="metric-card">
                <h3>Math Blocks</h3>
                <div class="metric-value">{before['total_math_blocks']}</div>
            </div>
            <div class="metric-card">
                <h3>Table Blocks</h3>
                <div class="metric-value">{before['total_table_blocks']}</div>
            </div>
        </div>
"""
    
    # Add after metrics
    if "after_aggregate" in summary:
        after = summary["after_aggregate"]
        
        def score_class(score: float) -> str:
            if score >= 0.9:
                return "score-excellent"
            elif score >= 0.7:
                return "score-good"
            else:
                return "score-poor"
        
        html += f"""
        <h2>✨ After Translation (Quality Analysis)</h2>
        <div class="metric-grid">
            <div class="metric-card">
                <h3>Overall Score</h3>
                <div class="metric-value {score_class(after['avg_overall_score'])}">{after['avg_overall_score']:.3f}</div>
            </div>
            <div class="metric-card">
                <h3>Placeholder Score</h3>
                <div class="metric-value {score_class(after['avg_placeholder_score'])}">{after['avg_placeholder_score']:.3f}</div>
            </div>
            <div class="metric-card">
                <h3>Numeric Score</h3>
                <div class="metric-value {score_class(after['avg_numeric_score'])}">{after['avg_numeric_score']:.3f}</div>
            </div>
            <div class="metric-card">
                <h3>Format Score</h3>
                <div class="metric-value {score_class(after['avg_format_score'])}">{after['avg_format_score']:.3f}</div>
            </div>
            <div class="metric-card">
                <h3>Fluency Score</h3>
                <div class="metric-value {score_class(after['avg_fluency_score'])}">{after['avg_fluency_score']:.3f}</div>
            </div>
            <div class="metric-card">
                <h3>Fidelity Score</h3>
                <div class="metric-value {score_class(after['avg_fidelity_score'])}">{after['avg_fidelity_score']:.3f}</div>
            </div>
            <div class="metric-card">
                <h3>Total Issues</h3>
                <div class="metric-value score-poor">{after['total_issues']}</div>
            </div>
            <div class="metric-card">
                <h3>Total Warnings</h3>
                <div class="metric-value score-good">{after['total_warnings']}</div>
            </div>
        </div>
"""
    
    # Add overall performance
    if "overall_aggregate" in summary:
        overall = summary["overall_aggregate"]
        quality_class = score_class(overall['avg_document_quality'])
        confidence_class = score_class(overall['avg_document_confidence'])
        success_class = score_class(overall['block_success_rate'])
        
        html += f"""
        <h2>⚡ Overall Performance</h2>
        <div class="metric-grid">
            <div class="metric-card">
                <h3>Document Quality</h3>
                <div class="metric-value {quality_class}">{overall['avg_document_quality']:.1%}</div>
            </div>
            <div class="metric-card">
                <h3>Document Confidence</h3>
                <div class="metric-value {confidence_class}">{overall['avg_document_confidence']:.1%}</div>
            </div>
            <div class="metric-card">
                <h3>Block Success Rate</h3>
                <div class="metric-value {success_class}">{overall['block_success_rate']:.1%}</div>
            </div>
            <div class="metric-card">
                <h3>Total Processing Time</h3>
                <div class="metric-value">{overall['total_elapsed_seconds']:.1f}s</div>
            </div>
        </div>
"""
    
    # Add per-test results table
    html += """
        <h2>📑 Per-Test Results</h2>
        <table>
            <thead>
                <tr>
                    <th>Test Name</th>
                    <th>Quality</th>
                    <th>Confidence</th>
                    <th>Blocks OK</th>
                    <th>Blocks Failed</th>
                    <th>Time (s)</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
"""
    
    valid_results = [r for r in results if r["has_output"]]
    for r in valid_results:
        metrics = r.get("metrics", {}).get("overall", {})
        quality = metrics.get("document_quality", 0)
        confidence = metrics.get("document_confidence", 0)
        blocks_ok = metrics.get("blocks_ok", 0)
        blocks_failed = metrics.get("blocks_failed", 0)
        elapsed = metrics.get("elapsed_seconds", 0)
        
        if quality >= 0.9 and confidence >= 0.9:
            status = "✅ EXCELLENT"
            status_class = "score-excellent"
        elif quality >= 0.7 and confidence >= 0.7:
            status = "⚠️ GOOD"
            status_class = "score-good"
        else:
            status = "❌ NEEDS WORK"
            status_class = "score-poor"
        
        html += f"""
                <tr>
                    <td>{r['test_name']}</td>
                    <td class="{score_class(quality)}">{quality:.1%}</td>
                    <td class="{score_class(confidence)}">{confidence:.1%}</td>
                    <td>{blocks_ok}</td>
                    <td>{blocks_failed}</td>
                    <td>{elapsed:.1f}</td>
                    <td class="{status_class}">{status}</td>
                </tr>
"""
    
    html += """
            </tbody>
        </table>
    </div>
</body>
</html>
"""
    
    with open(output_path, 'w') as f:
        f.write(html)
    
    print(f"✅ HTML report saved to: {output_path}")


def main():
    """Main entry point."""
    # Get project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    outputs_dir = project_root / "outputs"
    
    if not outputs_dir.exists():
        print(f"❌ Error: Outputs directory not found: {outputs_dir}")
        sys.exit(1)
    
    print(f"🔍 Analyzing outputs in: {outputs_dir}")
    
    # Collect all test case directories
    test_dirs = [d for d in outputs_dir.iterdir() if d.is_dir() and (d / "report.json").exists()]
    
    if not test_dirs:
        print("❌ No test outputs found!")
        sys.exit(1)
    
    print(f"📂 Found {len(test_dirs)} test outputs\n")
    
    # Analyze each test case
    results = []
    for test_dir in sorted(test_dirs):
        print(f"  Analyzing: {test_dir.name}...")
        result = analyze_test_case(test_dir)
        results.append(result)
    
    # Generate summary
    summary = generate_summary_stats(results)
    
    # Print colored terminal report
    print_colored_report(summary, results)
    
    # Save JSON report
    json_report_path = project_root / "quality_report.json"
    with open(json_report_path, 'w') as f:
        json.dump({
            "summary": summary,
            "results": results
        }, f, indent=2)
    print(f"✅ JSON report saved to: {json_report_path}")
    
    # Generate HTML report
    html_report_path = project_root / "quality_report.html"
    generate_html_report(summary, results, html_report_path)
    
    print(f"\n{Colors.OKGREEN}{Colors.BOLD}✨ Quality report generation complete!{Colors.ENDC}\n")


if __name__ == "__main__":
    main()
