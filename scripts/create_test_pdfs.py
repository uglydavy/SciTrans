#!/usr/bin/env python3
"""Generate test PDFs with various characteristics for validating SciTrans.

Creates 10 test PDFs covering different scenarios:
1. Simple text
2. Math equations
3. Bullet lists
4. Tables (text-based)
5. Mixed fonts
6. Long paragraphs
7. Citations and URLs
8. Multi-column layout
9. Scientific paper structure
10. Complex real-world example
"""

from pathlib import Path

import fitz  # PyMuPDF


def create_test_pdf_1_simple_text(output_dir: Path):
    """1. Simple text - Basic translation test."""
    doc = fitz.open()
    page = doc.new_page(width=400, height=300)

    page.insert_text((50, 50), "Hello World", fontsize=14)
    page.insert_text((50, 80), "This is a simple test document.", fontsize=11)
    page.insert_text((50, 100), "It contains basic English text.", fontsize=11)
    page.insert_text((50, 120), "No special formatting or math.", fontsize=11)

    doc.save(output_dir / "01_simple_text.pdf")
    doc.close()
    print("✓ Created: 01_simple_text.pdf")


def create_test_pdf_2_math_equations(output_dir: Path):
    """2. Math equations - Test math preservation."""
    doc = fitz.open()
    page = doc.new_page(width=500, height=400)

    page.insert_text((50, 50), "Mathematical Equations", fontsize=14)
    page.insert_text((50, 80), "Einstein's famous equation is $E=mc^2$ where", fontsize=11)
    page.insert_text((50, 100), "E is energy, m is mass, and c is the speed of light.", fontsize=11)
    page.insert_text(
        (50, 130), "The quadratic formula: $$x = \\frac{-b \\pm \\sqrt{b^2-4ac}}{2a}$$", fontsize=11
    )
    page.insert_text(
        (50, 160), "Inline math like $\\alpha + \\beta = \\gamma$ should be preserved.", fontsize=11
    )
    page.insert_text((50, 190), "Display math:", fontsize=11)
    page.insert_text(
        (50, 210), "\\[\\int_0^\\infty e^{-x^2} dx = \\frac{\\sqrt{\\pi}}{2}\\]", fontsize=11
    )

    doc.save(output_dir / "02_math_equations.pdf")
    doc.close()
    print("✓ Created: 02_math_equations.pdf")


def create_test_pdf_3_bullet_lists(output_dir: Path):
    """3. Bullet lists - Test format preservation."""
    doc = fitz.open()
    page = doc.new_page(width=450, height=500)

    page.insert_text((50, 50), "Research Objectives", fontsize=14)
    page.insert_text((50, 80), "The main goals of this study are:", fontsize=11)
    page.insert_text((70, 110), "• Develop a novel translation system", fontsize=11)
    page.insert_text((70, 130), "• Preserve mathematical content accurately", fontsize=11)
    page.insert_text((70, 150), "• Maintain document layout and structure", fontsize=11)
    page.insert_text((70, 170), "• Support multiple translation backends", fontsize=11)

    page.insert_text((50, 210), "Methodology:", fontsize=11)
    page.insert_text((70, 240), "1. Extract text from PDF using PyMuPDF", fontsize=11)
    page.insert_text((70, 260), "2. Apply masking to protect sensitive content", fontsize=11)
    page.insert_text((70, 280), "3. Translate using selected backend", fontsize=11)
    page.insert_text((70, 300), "4. Render translated text with layout preservation", fontsize=11)

    doc.save(output_dir / "03_bullet_lists.pdf")
    doc.close()
    print("✓ Created: 03_bullet_lists.pdf")


def create_test_pdf_4_tables(output_dir: Path):
    """4. Tables - Test table handling."""
    doc = fitz.open()
    page = doc.new_page(width=500, height=400)

    page.insert_text((50, 50), "Experimental Results", fontsize=14)
    page.insert_text((50, 80), "Table 1: Performance Comparison", fontsize=11)

    # Table header
    page.insert_text((70, 110), "Method", fontsize=10)
    page.insert_text((200, 110), "Accuracy", fontsize=10)
    page.insert_text((320, 110), "Speed (ms)", fontsize=10)

    # Table rows
    page.insert_text((70, 130), "Baseline", fontsize=10)
    page.insert_text((200, 130), "85.3%", fontsize=10)
    page.insert_text((320, 130), "42.5", fontsize=10)

    page.insert_text((70, 150), "Proposed", fontsize=10)
    page.insert_text((200, 150), "92.7%", fontsize=10)
    page.insert_text((320, 150), "38.2", fontsize=10)

    page.insert_text((70, 170), "Advanced", fontsize=10)
    page.insert_text((200, 170), "94.1%", fontsize=10)
    page.insert_text((320, 170), "45.8", fontsize=10)

    page.insert_text((50, 200), "As shown in Table 1, the proposed method achieves", fontsize=11)
    page.insert_text((50, 220), "92.7% accuracy with 38.2 ms processing time.", fontsize=11)

    doc.save(output_dir / "04_tables.pdf")
    doc.close()
    print("✓ Created: 04_tables.pdf")


def create_test_pdf_5_mixed_fonts(output_dir: Path):
    """5. Mixed fonts - Test font handling."""
    doc = fitz.open()
    page = doc.new_page(width=500, height=400)

    page.insert_text((50, 50), "Typography Test", fontsize=16)
    page.insert_text((50, 80), "Normal text in Helvetica.", fontsize=11)
    page.insert_text((50, 100), "Bold text for emphasis.", fontsize=11)
    page.insert_text((50, 120), "Italic text for scientific names.", fontsize=11)
    page.insert_text((50, 140), "Bold italic combination.", fontsize=11)

    page.insert_text((50, 170), "Different sizes:", fontsize=11)
    page.insert_text((50, 190), "Small text", fontsize=8)
    page.insert_text((150, 190), "Normal text", fontsize=11)
    page.insert_text((270, 190), "Large text", fontsize=14)

    doc.save(output_dir / "05_mixed_fonts.pdf")
    doc.close()
    print("✓ Created: 05_mixed_fonts.pdf")


def create_test_pdf_6_long_paragraphs(output_dir: Path):
    """6. Long paragraphs - Test overflow handling."""
    doc = fitz.open()
    page = doc.new_page(width=500, height=600)

    page.insert_text((50, 50), "Abstract", fontsize=14)

    abstract = (
        "This paper presents a novel approach to scientific document translation "
        "that preserves mathematical content, layout structure, and formatting. "
        "Unlike traditional translation systems that treat documents as plain text, "
        "our method extracts structured information from PDF files and applies "
        "content-aware translation strategies. We introduce a masking mechanism "
        "to protect mathematical expressions and implement a font-fitting algorithm "
        "to maintain the original document layout. Experimental results on a corpus "
        "of scientific papers demonstrate that our approach achieves high translation "
        "quality while preserving document structure with 95% layout fidelity."
    )

    # Insert long paragraph (will test word wrapping)
    rect = fitz.Rect(50, 80, 450, 300)
    page.insert_textbox(rect, abstract, fontsize=11, align=fitz.TEXT_ALIGN_LEFT)

    page.insert_text((50, 320), "Introduction", fontsize=14)
    intro = (
        "Scientific communication across languages is essential in today's "
        "globalized research environment. However, translating scientific documents "
        "poses unique challenges due to the presence of mathematical notation, "
        "technical terminology, and complex document structures."
    )
    rect2 = fitz.Rect(50, 350, 450, 500)
    page.insert_textbox(rect2, intro, fontsize=11, align=fitz.TEXT_ALIGN_LEFT)

    doc.save(output_dir / "06_long_paragraphs.pdf")
    doc.close()
    print("✓ Created: 06_long_paragraphs.pdf")


def create_test_pdf_7_citations_urls(output_dir: Path):
    """7. Citations and URLs - Test masking."""
    doc = fitz.open()
    page = doc.new_page(width=500, height=450)

    page.insert_text((50, 50), "References and Links", fontsize=14)

    page.insert_text((50, 80), "Previous work [1, 2, 3] has shown that machine", fontsize=11)
    page.insert_text((50, 100), "learning can improve translation quality [4].", fontsize=11)

    page.insert_text((50, 130), "For more information, visit:", fontsize=11)
    page.insert_text((50, 150), "https://example.com/research", fontsize=11)
    page.insert_text((50, 170), "or contact: researcher@university.edu", fontsize=11)

    page.insert_text((50, 200), "The code is available at:", fontsize=11)
    page.insert_text((50, 220), "www.github.com/example/repo", fontsize=11)

    page.insert_text((50, 260), "References", fontsize=12)
    page.insert_text((50, 290), "[1] Smith et al. (2020). Neural translation.", fontsize=10)
    page.insert_text((50, 310), "[2] Johnson (2021). PDF processing.", fontsize=10)
    page.insert_text((50, 330), "[3] Lee and Kim (2022). Layout preservation.", fontsize=10)
    page.insert_text((50, 350), "[4] Brown et al. (2023). Quality metrics.", fontsize=10)

    doc.save(output_dir / "07_citations_urls.pdf")
    doc.close()
    print("✓ Created: 07_citations_urls.pdf")


def create_test_pdf_8_multicolumn(output_dir: Path):
    """8. Multi-column layout - Test reading order."""
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)

    # Title spanning both columns
    page.insert_text((50, 50), "Two-Column Scientific Paper", fontsize=14)

    # Left column
    page.insert_text((50, 90), "Abstract", fontsize=12)
    rect1 = fitz.Rect(50, 110, 280, 350)
    page.insert_textbox(
        rect1,
        "This is the left column. It contains the abstract and introduction sections. "
        "The text should be extracted in the correct reading order.",
        fontsize=10,
        align=fitz.TEXT_ALIGN_LEFT,
    )

    page.insert_text((50, 360), "Introduction", fontsize=12)
    rect2 = fitz.Rect(50, 380, 280, 600)
    page.insert_textbox(
        rect2,
        "The introduction provides background information. "
        "Multi-column layouts are common in academic papers.",
        fontsize=10,
        align=fitz.TEXT_ALIGN_LEFT,
    )

    # Right column
    page.insert_text((320, 90), "Methods", fontsize=12)
    rect3 = fitz.Rect(320, 110, 550, 350)
    page.insert_textbox(
        rect3,
        "This is the right column. It describes the methodology. "
        "Reading order should go: left column top to bottom, then right column.",
        fontsize=10,
        align=fitz.TEXT_ALIGN_LEFT,
    )

    page.insert_text((320, 360), "Results", fontsize=12)
    rect4 = fitz.Rect(320, 380, 550, 600)
    page.insert_textbox(
        rect4,
        "The results section presents experimental findings. "
        "Proper column detection is crucial for correct translation.",
        fontsize=10,
        align=fitz.TEXT_ALIGN_LEFT,
    )

    doc.save(output_dir / "08_multicolumn.pdf")
    doc.close()
    print("✓ Created: 08_multicolumn.pdf")


def create_test_pdf_9_scientific_paper(output_dir: Path):
    """9. Scientific paper structure - Realistic test."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4 size

    # Title
    page.insert_text((50, 50), "Machine Learning for Document Translation:", fontsize=14)
    page.insert_text((50, 70), "A Novel Approach", fontsize=14)

    # Authors
    page.insert_text((50, 100), "John Smith, Jane Doe, Alice Johnson", fontsize=11)
    page.insert_text((50, 120), "University A, Institute B", fontsize=10)

    # Abstract
    page.insert_text((50, 160), "Abstract", fontsize=12)
    abstract_rect = fitz.Rect(50, 180, 545, 280)
    page.insert_textbox(
        abstract_rect,
        "We present a machine learning approach to scientific document translation "
        "that preserves mathematical notation ($\\alpha$, $\\beta$) and layout structure. "
        "Our method achieves 92.5% accuracy on a benchmark dataset.",
        fontsize=10,
    )

    # Keywords
    page.insert_text((50, 290), "Keywords:", fontsize=10)
    page.insert_text((120, 290), "translation, machine learning, NLP", fontsize=10)

    # Section 1
    page.insert_text((50, 330), "1. Introduction", fontsize=12)
    section1_rect = fitz.Rect(50, 350, 545, 480)
    page.insert_textbox(
        section1_rect,
        "Scientific communication requires accurate translation of technical content. "
        "Previous work [1, 2] has addressed general text translation, but preserving "
        "mathematical notation like $E=mc^2$ remains challenging.",
        fontsize=10,
    )

    # Section 2
    page.insert_text((50, 490), "2. Methodology", fontsize=12)
    section2_rect = fitz.Rect(50, 510, 545, 640)
    page.insert_textbox(
        section2_rect,
        "Our approach consists of three stages: (1) document parsing, (2) content masking, "
        "and (3) translation with layout preservation. The masking stage protects "
        "mathematical expressions using placeholders.",
        fontsize=10,
    )

    # Equation
    page.insert_text((50, 650), "The loss function is defined as:", fontsize=10)
    page.insert_text((50, 670), "$$L = \\sum_{i=1}^n (y_i - \\hat{y}_i)^2$$", fontsize=10)

    # Section 3
    page.insert_text((50, 700), "3. Results", fontsize=12)
    page.insert_text((50, 720), "Our experiments show that the proposed method", fontsize=10)
    page.insert_text((50, 740), "outperforms baseline approaches by 15%.", fontsize=10)

    doc.save(output_dir / "09_scientific_paper.pdf")
    doc.close()
    print("✓ Created: 09_scientific_paper.pdf")


def create_test_pdf_10_complex_realworld(output_dir: Path):
    """10. Complex real-world example - Stress test."""
    doc = fitz.open()

    # Page 1
    page1 = doc.new_page(width=595, height=842)
    page1.insert_text((50, 50), "Advanced Topics in Machine Translation", fontsize=16)
    page1.insert_text((50, 80), "Chapter 3: Neural Network Architectures", fontsize=14)

    # Mixed content
    content1_rect = fitz.Rect(50, 120, 545, 350)
    page1.insert_textbox(
        content1_rect,
        "The transformer architecture [Vaswani et al., 2017] revolutionized neural machine translation. "
        "The attention mechanism computes: $$\\text{Attention}(Q, K, V) = \\text{softmax}(\\frac{QK^T}{\\sqrt{d_k}})V$$ "
        "where $Q$, $K$, and $V$ are query, key, and value matrices. "
        "For more details, see https://arxiv.org/abs/1706.03762.",
        fontsize=10,
    )

    # Bullet points
    page1.insert_text((50, 370), "Key advantages:", fontsize=11)
    page1.insert_text((70, 395), "• Parallelizable training (unlike RNNs)", fontsize=10)
    page1.insert_text((70, 415), "• Captures long-range dependencies", fontsize=10)
    page1.insert_text((70, 435), "• State-of-the-art performance", fontsize=10)

    # Table
    page1.insert_text((50, 470), "Table 3.1: Model Comparison", fontsize=11)
    page1.insert_text((70, 500), "Model", fontsize=9)
    page1.insert_text((200, 500), "BLEU", fontsize=9)
    page1.insert_text((300, 500), "Parameters", fontsize=9)
    page1.insert_text((70, 520), "LSTM", fontsize=9)
    page1.insert_text((200, 520), "24.3", fontsize=9)
    page1.insert_text((300, 520), "100M", fontsize=9)
    page1.insert_text((70, 540), "Transformer", fontsize=9)
    page1.insert_text((200, 540), "28.7", fontsize=9)
    page1.insert_text((300, 540), "175M", fontsize=9)

    # More text
    content2_rect = fitz.Rect(50, 580, 545, 750)
    page1.insert_textbox(
        content2_rect,
        "Implementation details: The model was trained on 40GB of parallel text "
        "using Adam optimizer with $\\beta_1=0.9$ and $\\beta_2=0.98$. "
        "Learning rate schedule: $lr = d_{model}^{-0.5} \\cdot \\min(step^{-0.5}, step \\cdot warmup^{-1.5})$.",
        fontsize=10,
    )

    # Page 2
    page2 = doc.new_page(width=595, height=842)
    page2.insert_text((50, 50), "3.1 Attention Mechanisms", fontsize=14)

    content3_rect = fitz.Rect(50, 80, 545, 300)
    page2.insert_textbox(
        content3_rect,
        "Self-attention allows the model to attend to all positions in the input sequence. "
        "Multi-head attention extends this by projecting to multiple subspaces: "
        "$$\\text{MultiHead}(Q, K, V) = \\text{Concat}(head_1, ..., head_h)W^O$$ "
        "where $head_i = \\text{Attention}(QW_i^Q, KW_i^K, VW_i^V)$.",
        fontsize=10,
    )

    # Citations
    page2.insert_text((50, 320), "References", fontsize=12)
    page2.insert_text(
        (50, 350), "[1] Vaswani, A., et al. (2017). Attention is all you need.", fontsize=9
    )
    page2.insert_text((50, 370), "    NeurIPS. https://arxiv.org/abs/1706.03762", fontsize=9)
    page2.insert_text(
        (50, 395), "[2] Devlin, J., et al. (2019). BERT: Pre-training of deep", fontsize=9
    )
    page2.insert_text((50, 415), "    bidirectional transformers. NAACL.", fontsize=9)

    doc.save(output_dir / "10_complex_realworld.pdf")
    doc.close()
    print("✓ Created: 10_complex_realworld.pdf")


def main():
    """Generate all test PDFs."""
    output_dir = Path("test_pdfs")
    output_dir.mkdir(exist_ok=True)

    print("Creating test PDFs...")
    print("=" * 50)

    create_test_pdf_1_simple_text(output_dir)
    create_test_pdf_2_math_equations(output_dir)
    create_test_pdf_3_bullet_lists(output_dir)
    create_test_pdf_4_tables(output_dir)
    create_test_pdf_5_mixed_fonts(output_dir)
    create_test_pdf_6_long_paragraphs(output_dir)
    create_test_pdf_7_citations_urls(output_dir)
    create_test_pdf_8_multicolumn(output_dir)
    create_test_pdf_9_scientific_paper(output_dir)
    create_test_pdf_10_complex_realworld(output_dir)

    print("=" * 50)
    print(f"✓ All 10 test PDFs created in: {output_dir.absolute()}")
    print("\nTest PDFs:")
    for pdf_file in sorted(output_dir.glob("*.pdf")):
        print(f"  - {pdf_file.name}")


if __name__ == "__main__":
    main()
