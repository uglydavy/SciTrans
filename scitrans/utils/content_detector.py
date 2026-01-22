"""Content type detection for translation optimization.

Detects whether a document is academic/technical to adjust translation parameters.
"""

from enum import Enum
from dataclasses import dataclass
import re
from typing import Optional

from scitrans.core.models import Document, Block


class ContentType(Enum):
    """Document content types."""
    ACADEMIC = "academic"  # Technical/academic papers
    GENERAL = "general"    # General documents


@dataclass
class ContentAnalysis:
    """Analysis results for content type detection."""
    content_type: ContentType
    score: float  # 0-100
    technical_keyword_count: int
    citation_count: int
    math_density: float
    has_academic_structure: bool
    reasoning: str


# Technical/academic keywords that appear in research papers
TECHNICAL_KEYWORDS = {
    # AI/ML terms
    "GPT", "RLHF", "InstructGPT", "neural", "algorithm", "model", "transformer",
    "attention", "embedding", "layer", "training", "fine-tuning", "reinforcement",
    "dataset", "benchmark", "evaluation", "learning", "optimization",
    
    # Research terms
    "hypothesis", "methodology", "experiment", "results", "conclusion",
    "abstract", "introduction", "discussion", "validation", "analysis",
    
    # Math/stats terms
    "equation", "theorem", "proof", "coefficient", "variable", "parameter",
    "distribution", "statistical", "probability", "correlation",
    
    # Scientific terms
    "research", "study", "investigation", "observation", "measurement",
    "procedure", "protocol", "sample", "control", "significant",
}

# Academic section headers
ACADEMIC_HEADERS = {
    "abstract", "introduction", "related work", "methodology", "methods",
    "experiments", "results", "discussion", "conclusion", "references",
    "acknowledgments", "appendix", "background"
}

# Technical terms that are VALID when identical in source/target languages
# These terms should NOT be flagged as identity translations
TECHNICAL_TERM_WHITELIST = {
    # AI/ML Models
    "GPT", "GPT-2", "GPT-3", "GPT-4", "DALL-E", "DALL-E 2", "CLIP",
    "InstructGPT", "ChatGPT", "BERT", "ViT", "ResNet", "LSTM", "RNN",
    "Transformer", "RLHF", "VAE", "GAN", "CNN", "YOLO", "AlexNet",
    
    # Programming/Tech
    "Python", "PyTorch", "TensorFlow", "NumPy", "API", "HTTP", "JSON",
    "GPU", "CPU", "RAM", "URL", "HTML", "CSS", "SQL", "REST", "XML",
    "JavaScript", "TypeScript", "Docker", "Kubernetes", "Git",
    
    # Scientific
    "DNA", "RNA", "pH", "MHz", "GHz", "kHz", "nm", "μm", "mL", "kg",
    "CRISPR", "PCR", "ATP", "RNA-seq",
    
    # Acronyms
    "AI", "ML", "NLP", "CV", "RL", "DL", "IoT", "5G", "4G", "LTE",
    "VR", "AR", "MR", "IoT", "SaaS", "PaaS", "IaaS",
}


def contains_whitelisted_terms(text: str) -> bool:
    """Check if text contains whitelisted technical terms.
    
    Technical terms in the whitelist are valid when identical in both
    source and target languages (e.g., "GPT-3" → "GPT-3" is correct).
    
    Args:
        text: Text to check for whitelisted terms
        
    Returns:
        True if text contains any whitelisted technical term
    """
    if not text:
        return False
    
    text_upper = text.upper()
    for term in TECHNICAL_TERM_WHITELIST:
        if term.upper() in text_upper:
            return True
    return False


def detect_content_type(doc: Document) -> ContentAnalysis:
    """Detect if document is technical/academic based on multiple indicators.
    
    Analyzes:
    - Technical keywords (GPT, RLHF, neural, algorithm, etc.)
    - Citation patterns: (Author, 2020), [1], et al.
    - Math/equation density: % blocks containing @@MATH_
    - Academic structure: Abstract, Introduction, Methods, Results
    
    Args:
        doc: Parsed document
        
    Returns:
        ContentAnalysis with content type and reasoning
    """
    
    # Extract all text blocks
    all_text = []
    header_texts = []
    math_count = 0
    total_blocks = 0
    
    for page in doc.pages:
        for block in page.blocks:
            total_blocks += 1
            text = _get_block_text(block)
            all_text.append(text.lower())
            
            # Check if header
            if block.meta.get("is_header") or block.meta.get("block_type") in ["title", "header", "subheader"]:
                header_texts.append(text.lower())
            
            # Count math blocks
            if "@@MATH_" in text or "@@SCITRANS_MATH_" in text:
                math_count += 1
    
    # Combine all text for analysis
    full_text = " ".join(all_text)
    full_text_lower = full_text.lower()
    
    # Metric 1: Technical keyword count (0-40 points)
    keyword_count = sum(1 for keyword in TECHNICAL_KEYWORDS if keyword.lower() in full_text_lower)
    keyword_score = min(40, keyword_count * 2)  # 2 points per keyword, max 40
    
    # Metric 2: Citation patterns (0-20 points)
    citation_patterns = [
        r'\([A-Z][a-z]+(?:\s+et\s+al\.?)?,?\s+\d{4}\)',  # (Author, 2020) or (Author et al., 2020)
        r'\[\d+\]',  # [1], [2]
        r'\bet\s+al\.',  # et al.
    ]
    citation_count = 0
    for pattern in citation_patterns:
        citation_count += len(re.findall(pattern, full_text))
    citation_score = min(20, citation_count)  # 1 point per citation, max 20
    
    # Metric 3: Math density (0-20 points)
    math_density = math_count / total_blocks if total_blocks > 0 else 0.0
    math_score = min(20, math_density * 100)  # Convert to percentage, max 20
    
    # Metric 4: Academic structure (0-20 points)
    has_academic_structure = False
    structure_matches = 0
    for header in header_texts:
        for academic_header in ACADEMIC_HEADERS:
            if academic_header in header:
                structure_matches += 1
                break
    
    if structure_matches >= 3:  # At least 3 academic sections
        has_academic_structure = True
        structure_score = 20
    elif structure_matches >= 1:
        structure_score = 10
    else:
        structure_score = 0
    
    # Total score (0-100)
    total_score = keyword_score + citation_score + math_score + structure_score
    
    # Determine content type (threshold: 60)
    if total_score >= 60:
        content_type = ContentType.ACADEMIC
        reasoning = f"Academic content detected (score: {total_score:.0f}/100): {keyword_count} technical keywords, {citation_count} citations, {math_density*100:.1f}% math blocks, {'academic structure' if has_academic_structure else 'no clear structure'}"
    else:
        content_type = ContentType.GENERAL
        reasoning = f"General content (score: {total_score:.0f}/100): Below academic threshold (60)"
    
    return ContentAnalysis(
        content_type=content_type,
        score=total_score,
        technical_keyword_count=keyword_count,
        citation_count=citation_count,
        math_density=math_density,
        has_academic_structure=has_academic_structure,
        reasoning=reasoning
    )


def _get_block_text(block: Block) -> str:
    """Extract text from a block."""
    parts = []
    for line in block.lines:
        for span in line.spans:
            parts.append(span.text)
    return " ".join(parts)
