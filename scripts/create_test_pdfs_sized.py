#!/usr/bin/env python3
"""Generate test PDFs with specific page counts for testing SciTrans.

Creates 3 test PDFs:
1. Small: 1-3 pages (simple document)
2. Medium: 5-12 pages (moderate complexity)
3. Large: 50+ pages (stress test)
"""

from pathlib import Path

import fitz  # PyMuPDF


def create_small_pdf(output_dir: Path):
    """Create a small PDF (1-3 pages) for basic testing."""
    doc = fitz.open()
    
    # Page 1
    page1 = doc.new_page(width=595, height=842)  # A4
    page1.insert_text((50, 50), "Small Test Document", fontsize=16)
    page1.insert_text((50, 80), "This is a simple test document with basic content.", fontsize=11)
    page1.insert_text((50, 110), "It contains a few paragraphs of English text.", fontsize=11)
    
    abstract_rect = fitz.Rect(50, 140, 545, 300)
    page1.insert_textbox(
        abstract_rect,
        "This document is designed to test the translation pipeline with a small PDF. "
        "It should translate quickly and demonstrate basic functionality. "
        "The content includes simple sentences and basic formatting.",
        fontsize=11,
    )
    
    page1.insert_text((50, 320), "Section 1: Introduction", fontsize=12)
    section1_rect = fitz.Rect(50, 350, 545, 500)
    page1.insert_textbox(
        section1_rect,
        "This section introduces the topic. It contains multiple sentences that form "
        "a coherent paragraph. The translation system should preserve the structure "
        "and meaning of this text.",
        fontsize=11,
    )
    
    page1.insert_text((50, 520), "Section 2: Methodology", fontsize=12)
    section2_rect = fitz.Rect(50, 550, 545, 700)
    page1.insert_textbox(
        section2_rect,
        "The methodology section describes the approach. It includes details about "
        "the process and techniques used. This content should be translated accurately.",
        fontsize=11,
    )
    
    # Page 2 (optional - can be 1-3 pages)
    page2 = doc.new_page(width=595, height=842)
    page2.insert_text((50, 50), "Section 3: Results", fontsize=12)
    results_rect = fitz.Rect(50, 80, 545, 400)
    page2.insert_textbox(
        results_rect,
        "The results section presents findings from the study. It includes data analysis "
        "and interpretation. The translation should maintain the technical accuracy of "
        "the content while making it accessible in the target language.",
        fontsize=11,
    )
    
    page2.insert_text((50, 420), "Conclusion", fontsize=12)
    conclusion_rect = fitz.Rect(50, 450, 545, 600)
    page2.insert_textbox(
        conclusion_rect,
        "In conclusion, this test document demonstrates basic translation capabilities. "
        "It should process quickly and produce accurate results.",
        fontsize=11,
    )
    
    num_pages = len(doc)
    doc.save(output_dir / "small_test.pdf")
    doc.close()
    print(f"✓ Created: small_test.pdf ({num_pages} pages)")


def create_medium_pdf(output_dir: Path):
    """Create a medium PDF (5-12 pages) for moderate testing."""
    doc = fitz.open()
    
    # Create 8 pages of content
    for page_num in range(8):
        page = doc.new_page(width=595, height=842)  # A4
        
        # Title on first page
        if page_num == 0:
            page.insert_text((50, 50), "Medium Test Document", fontsize=16)
            page.insert_text((50, 80), "A comprehensive test document with multiple sections", fontsize=12)
        
        # Section header
        section_num = page_num + 1
        page.insert_text((50, 50 if page_num > 0 else 120), f"Section {section_num}", fontsize=14)
        
        # Content
        y_start = 80 if page_num > 0 else 150
        content_rect = fitz.Rect(50, y_start, 545, 750)
        
        content = (
            f"This is section {section_num} of the medium test document. "
            f"It contains detailed information about various topics. "
            f"The content is designed to test the translation pipeline with a moderate-sized PDF. "
            f"Each section includes multiple paragraphs with technical terminology and complex sentences. "
            f"The translation system should handle this volume of content efficiently. "
            f"Mathematical expressions like $E=mc^2$ may appear in scientific contexts. "
            f"Citations such as [1, 2, 3] are also common in academic documents. "
            f"This section continues with additional content to fill the page adequately. "
            f"The goal is to create a realistic test case for the translation pipeline."
        )
        
        page.insert_textbox(content_rect, content, fontsize=11)
        
        # Add some variety
        if page_num % 2 == 0:
            page.insert_text((50, 770), f"• Key point for section {section_num}", fontsize=10)
            page.insert_text((50, 790), f"• Another important note", fontsize=10)
        else:
            page.insert_text((50, 770), f"Reference: See section {section_num - 1} for related information.", fontsize=10)
    
    num_pages = len(doc)
    doc.save(output_dir / "medium_test.pdf")
    doc.close()
    print(f"✓ Created: medium_test.pdf ({num_pages} pages)")


def create_large_pdf(output_dir: Path):
    """Create a large PDF (50+ pages) for stress testing."""
    doc = fitz.open()
    
    # Create 55 pages of content
    total_pages = 55
    for page_num in range(total_pages):
        page = doc.new_page(width=595, height=842)  # A4
        
        # Title on first page
        if page_num == 0:
            page.insert_text((50, 50), "Large Test Document", fontsize=16)
            page.insert_text((50, 80), "A comprehensive stress test document", fontsize=12)
            page.insert_text((50, 110), f"Total pages: {total_pages}", fontsize=11)
            y_start = 150
        else:
            y_start = 50
        
        # Section header (every 5 pages)
        if page_num % 5 == 0:
            section_num = (page_num // 5) + 1
            page.insert_text((50, y_start), f"Chapter {section_num}", fontsize=14)
            y_start += 40
        
        # Subsection
        subsection_num = (page_num % 5) + 1
        page.insert_text((50, y_start), f"Section {page_num + 1}.{subsection_num}", fontsize=12)
        y_start += 30
        
        # Content
        content_rect = fitz.Rect(50, y_start, 545, 750)
        
        content = (
            f"This is page {page_num + 1} of {total_pages} in the large test document. "
            f"It contains extensive content designed to stress-test the translation pipeline. "
            f"The document includes multiple chapters, sections, and subsections. "
            f"Each page contains detailed information with technical terminology. "
            f"Mathematical expressions such as $\\alpha + \\beta = \\gamma$ appear throughout. "
            f"Citations like [Smith et al., 2020] and [Johnson, 2021] are included. "
            f"URLs such as https://example.com/research are also present. "
            f"The content is structured to simulate a real academic paper or technical document. "
            f"This page continues with additional paragraphs to ensure adequate content density. "
            f"The translation system must handle this volume efficiently without errors. "
            f"Performance and accuracy are both important considerations for large documents."
        )
        
        page.insert_textbox(content_rect, content, fontsize=11)
        
        # Add footer with page number
        page.insert_text((500, 820), f"Page {page_num + 1}", fontsize=9)
        
        # Add variety every few pages
        if page_num % 3 == 0:
            page.insert_text((50, 770), "• Important note for this section", fontsize=10)
        elif page_num % 7 == 0:
            page.insert_text((50, 770), "Table {}.1: Sample data".format(page_num // 7 + 1), fontsize=10)
            page.insert_text((70, 790), "Item A: Value 1", fontsize=9)
            page.insert_text((70, 810), "Item B: Value 2", fontsize=9)
    
    num_pages = len(doc)
    doc.save(output_dir / "large_test.pdf")
    doc.close()
    print(f"✓ Created: large_test.pdf ({num_pages} pages)")


def main():
    """Generate all sized test PDFs."""
    output_dir = Path("test_pdfs")
    output_dir.mkdir(exist_ok=True)

    print("Creating sized test PDFs...")
    print("=" * 50)

    create_small_pdf(output_dir)
    create_medium_pdf(output_dir)
    create_large_pdf(output_dir)

    print("=" * 50)
    print(f"✓ All sized test PDFs created in: {output_dir.absolute()}")
    print("\nTest PDFs:")
    for pdf_file in sorted(output_dir.glob("*_test.pdf")):
        print(f"  - {pdf_file.name}")


if __name__ == "__main__":
    main()

