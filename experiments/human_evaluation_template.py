#!/usr/bin/env python3
"""Human evaluation data collection tool.

Generates evaluation forms and collects ratings for correlation analysis.
"""

import json
from pathlib import Path


def create_evaluation_form(output_dir: str, translated_dir: str):
    """Create HTML evaluation form for human raters."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Find all translated documents
    translated_path = Path(translated_dir)
    reports = list(translated_path.glob("*/report.json"))

    html_template = """<!DOCTYPE html>
<html>
<head>
    <title>SciTrans-LLMs Translation Quality Evaluation</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 900px; margin: 20px auto; padding: 20px; }
        h1 { color: #2c3e50; }
        .document { border: 1px solid #ddd; padding: 20px; margin: 20px 0; border-radius: 5px; }
        .block { background: #f8f9fa; padding: 15px; margin: 10px 0; border-left: 4px solid #3498db; }
        .rating { margin: 10px 0; }
        label { display: inline-block; width: 200px; font-weight: bold; }
        select, input { padding: 5px; margin: 5px; }
        button { background: #3498db; color: white; padding: 10px 20px; border: none; cursor: pointer; border-radius: 5px; margin: 10px 5px; }
        button:hover { background: #2980b9; }
        .instructions { background: #e8f4f8; padding: 15px; border-radius: 5px; margin: 20px 0; }
    </style>
</head>
<body>
    <h1>🎓 SciTrans-LLMs Translation Quality Evaluation</h1>
    
    <div class="instructions">
        <h3>Instructions for Raters</h3>
        <p>Please evaluate each translation on the following dimensions (1-5 scale):</p>
        <ul>
            <li><strong>Adequacy:</strong> Is the meaning preserved? (1=not at all, 5=perfectly)</li>
            <li><strong>Fluency:</strong> Is it natural French? (1=incomprehensible, 5=native-like)</li>
            <li><strong>Math Preservation:</strong> Are equations correct? (1=corrupted, 5=perfect, N/A if no math)</li>
            <li><strong>Format Preservation:</strong> Is structure maintained? (1=broken, 5=identical)</li>
            <li><strong>Overall Quality:</strong> Overall impression (1=unacceptable, 5=excellent)</li>
        </ul>
        <p><strong>Rater ID:</strong> <input type="text" id="rater_id" placeholder="Your initials"></p>
    </div>
    
    <form id="evaluation_form">
"""

    # Add evaluation sections for each document
    for idx, report_file in enumerate(reports[:5], 1):  # Limit to 5 for human eval
        report = json.load(open(report_file))
        doc_name = report["input_pdf"]

        html_template += f"""
        <div class="document">
            <h3>Document {idx}: {Path(doc_name).name}</h3>
            <p><strong>Blocks:</strong> {report["num_blocks"]} | <strong>Automated Score:</strong> {report["scoring"]["document_quality"]:.2%}</p>
            
            <div class="rating">
                <label>Adequacy (1-5):</label>
                <select name="doc{idx}_adequacy">
                    <option value="">Select...</option>
                    <option value="1">1 - Very Poor</option>
                    <option value="2">2 - Poor</option>
                    <option value="3">3 - Acceptable</option>
                    <option value="4">4 - Good</option>
                    <option value="5">5 - Excellent</option>
                </select>
            </div>
            
            <div class="rating">
                <label>Fluency (1-5):</label>
                <select name="doc{idx}_fluency">
                    <option value="">Select...</option>
                    <option value="1">1 - Very Poor</option>
                    <option value="2">2 - Poor</option>
                    <option value="3">3 - Acceptable</option>
                    <option value="4">4 - Good</option>
                    <option value="5">5 - Excellent</option>
                </select>
            </div>
            
            <div class="rating">
                <label>Math Preservation (1-5/N/A):</label>
                <select name="doc{idx}_math">
                    <option value="">Select...</option>
                    <option value="NA">N/A (no math)</option>
                    <option value="1">1 - Corrupted</option>
                    <option value="2">2 - Mostly broken</option>
                    <option value="3">3 - Partially correct</option>
                    <option value="4">4 - Mostly correct</option>
                    <option value="5">5 - Perfect</option>
                </select>
            </div>
            
            <div class="rating">
                <label>Format Preservation (1-5):</label>
                <select name="doc{idx}_format">
                    <option value="">Select...</option>
                    <option value="1">1 - Broken</option>
                    <option value="2">2 - Major issues</option>
                    <option value="3">3 - Acceptable</option>
                    <option value="4">4 - Good</option>
                    <option value="5">5 - Identical</option>
                </select>
            </div>
            
            <div class="rating">
                <label>Overall Quality (1-5):</label>
                <select name="doc{idx}_overall">
                    <option value="">Select...</option>
                    <option value="1">1 - Unacceptable</option>
                    <option value="2">2 - Poor</option>
                    <option value="3">3 - Acceptable</option>
                    <option value="4">4 - Good</option>
                    <option value="5">5 - Excellent</option>
                </select>
            </div>
            
            <div class="rating">
                <label>Comments:</label><br>
                <textarea name="doc{idx}_comments" rows="3" cols="70" placeholder="Optional comments"></textarea>
            </div>
        </div>
"""

    html_template += """
        <button type="button" onclick="saveEvaluation()">Save Evaluation</button>
        <button type="button" onclick="downloadJSON()">Download as JSON</button>
    </form>
    
    <script>
        function saveEvaluation() {
            const form = document.getElementById('evaluation_form');
            const data = new FormData(form);
            const ratings = { rater_id: document.getElementById('rater_id').value, evaluations: [] };
            
            // Parse form data
            for (let i = 1; i <= 10; i++) {
                if (data.get(`doc${i}_overall`)) {
                    ratings.evaluations.push({
                        doc_id: i,
                        adequacy: parseInt(data.get(`doc${i}_adequacy`) || 0),
                        fluency: parseInt(data.get(`doc${i}_fluency`) || 0),
                        math: data.get(`doc${i}_math`),
                        format: parseInt(data.get(`doc${i}_format`) || 0),
                        overall: parseInt(data.get(`doc${i}_overall`) || 0),
                        comments: data.get(`doc${i}_comments`) || ""
                    });
                }
            }
            
            // Save to localStorage
            localStorage.setItem('scitrans_evaluation', JSON.stringify(ratings));
            alert('Evaluation saved! Click "Download as JSON" to export.');
        }
        
        function downloadJSON() {
            const data = localStorage.getItem('scitrans_evaluation');
            if (!data) {
                alert('No evaluation data found. Please save first.');
                return;
            }
            
            const blob = new Blob([data], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'human_evaluation_' + new Date().toISOString().split('T')[0] + '.json';
            a.click();
        }
        
        // Load saved data if exists
        window.onload = function() {
            const saved = localStorage.getItem('scitrans_evaluation');
            if (saved) {
                const data = JSON.parse(saved);
                document.getElementById('rater_id').value = data.rater_id || '';
                // Restore form values (implement if needed)
            }
        };
    </script>
</body>
</html>
"""

    # Save HTML form
    form_file = output_path / "evaluation_form.html"
    form_file.write_text(html_template, encoding="utf-8")
    print(f"✓ Evaluation form created: {form_file}")
    print("\nInstructions:")
    print(f"  1. Open {form_file} in a web browser")
    print("  2. Review translated PDFs side-by-side with originals")
    print("  3. Fill in ratings for each document")
    print("  4. Click 'Save' then 'Download as JSON'")
    print("  5. Save the JSON file to experiments/results/exp1/human_ratings/")


if __name__ == "__main__":
    # Create evaluation form (analysis step removed)
    create_evaluation_form("experiments/results/exp1", "outputs")
