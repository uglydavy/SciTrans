"""Script to download real scientific PDFs for testing.

This script downloads publicly available scientific papers from arXiv
and other sources to create a comprehensive test suite.
"""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path

# List of scientific PDFs to download
# Using arXiv papers (public domain) and other open-access sources
PDF_URLS = [
    # Short papers (1-3 pages)
    ("https://arxiv.org/pdf/2301.00001.pdf", "arxiv_short_1.pdf"),  # Example - replace with real
    ("https://arxiv.org/pdf/2301.00002.pdf", "arxiv_short_2.pdf"),
    
    # Medium papers (5-12 pages)
    ("https://arxiv.org/pdf/2301.00003.pdf", "arxiv_medium_1.pdf"),
    ("https://arxiv.org/pdf/2301.00004.pdf", "arxiv_medium_2.pdf"),
    ("https://arxiv.org/pdf/2301.00005.pdf", "arxiv_medium_3.pdf"),
    
    # Large papers (20-50+ pages)
    ("https://arxiv.org/pdf/2301.00006.pdf", "arxiv_large_1.pdf"),
    ("https://arxiv.org/pdf/2301.00007.pdf", "arxiv_large_2.pdf"),
    ("https://arxiv.org/pdf/2301.00008.pdf", "arxiv_large_3.pdf"),
    ("https://arxiv.org/pdf/2301.00009.pdf", "arxiv_large_4.pdf"),
    ("https://arxiv.org/pdf/2301.00010.pdf", "arxiv_large_5.pdf"),
]

# Alternative: Use real arXiv papers (these are actual papers)
REAL_ARXIV_PAPERS = [
    # Popular recent papers that are likely to still be available
    ("https://arxiv.org/pdf/1706.03762.pdf", "attention_is_all_you_need.pdf"),  # Transformer paper
    ("https://arxiv.org/pdf/2010.11929.pdf", "vision_transformer.pdf"),  # ViT paper
    ("https://arxiv.org/pdf/2005.14165.pdf", "gpt3.pdf"),  # GPT-3 paper
    ("https://arxiv.org/pdf/2103.00020.pdf", "clip.pdf"),  # CLIP paper
    ("https://arxiv.org/pdf/2203.02155.pdf", "dalle2.pdf"),  # DALL-E 2 paper
]


def download_pdf(url: str, output_path: Path) -> bool:
    """Download a PDF from URL to output path.
    
    Returns True if successful, False otherwise.
    """
    try:
        print(f"Downloading {url}...")
        urllib.request.urlretrieve(url, output_path)
        if output_path.exists() and output_path.stat().st_size > 0:
            print(f"  ✓ Downloaded: {output_path.name} ({output_path.stat().st_size} bytes)")
            return True
        else:
            print(f"  ✗ Failed: File is empty or doesn't exist")
            return False
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False


def main():
    """Download scientific PDFs to test_pdfs directory."""
    test_pdfs_dir = Path("test_pdfs")
    test_pdfs_dir.mkdir(exist_ok=True)
    
    print("=" * 70)
    print("Downloading Scientific PDFs for Testing")
    print("=" * 70)
    print(f"Output directory: {test_pdfs_dir.absolute()}")
    print()
    
    # Try to download real arXiv papers
    downloaded = 0
    for url, filename in REAL_ARXIV_PAPERS:
        output_path = test_pdfs_dir / filename
        if output_path.exists():
            print(f"  ⊙ Skipping {filename} (already exists)")
            continue
        
        if download_pdf(url, output_path):
            downloaded += 1
    
    print()
    print("=" * 70)
    print(f"Download complete: {downloaded} new PDFs downloaded")
    print(f"Total PDFs in test_pdfs/: {len(list(test_pdfs_dir.glob('*.pdf')))}")
    print("=" * 70)
    
    if downloaded == 0:
        print()
        print("NOTE: No new PDFs were downloaded.")
        print("You can manually add scientific PDFs to the test_pdfs/ directory.")
        print("The system will work with any PDF files placed there.")


if __name__ == "__main__":
    main()

