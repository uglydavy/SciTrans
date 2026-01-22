"""Translation cleaner - removes instruction spillover and hallucinations."""

from __future__ import annotations

import logging
import re
from typing import Tuple

logger = logging.getLogger(__name__)


def clean_instruction_spillover(candidate: str) -> Tuple[str, bool]:
    """Clean instruction spillover and hallucinations from translated text.
    
    Args:
        candidate: The translated candidate string.
    
    Returns:
        A tuple of (cleaned_text, was_modified) where was_modified indicates if cleaning occurred.
    """
    if not candidate or not candidate.strip():
        return candidate, False
    
    original = candidate
    text = candidate.strip()
    
    # Step 1: Remove code fences and quotes
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    text = re.sub(r'^["\'](.+)["\']$', r'\1', text)
    
    # Step 2: Remove instruction prefixes (case-insensitive, at start of text)
    instruction_prefixes = [
        r'^here\s+is\s+the\s+translation:?\s*',
        r'^here\'s\s+the\s+translation:?\s*',
        r'^the\s+translation\s+is:?\s*',
        r'^translated\s+text:?\s*',
        r'^translation:?\s*',
        r'^output:?\s*',
        r'^result:?\s*',
        r'^voici\s+la\s+traduction:?\s*',
        r'^la\s+traduction\s+est:?\s*',
        r'^texte\s+traduit:?\s*',
        r'^traduction:?\s*',
        r'^sortie:?\s*',
        r'^résultat:?\s*',
    ]
    
    for pattern in instruction_prefixes:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        text = text.strip()
    
    # Step 3: Remove instruction-like sentences/paragraphs (line-by-line)
    # Split into lines first, then filter
    lines = text.split('\n')
    cleaned_lines = []
    
    # Instruction patterns to remove (comprehensive list - French and English)
    instruction_patterns = [
        # French instructions
        r"^n'oubliez pas\s*[:：].*",
        r".*n'oubliez pas\s*[:：].*",  # Catch mid-sentence too
        r"^rappel\s*[:：].*",
        r"^remarque\s*[:：].*",
        r"^attention\s*[:：].*",
        r"^note\s*[:：].*",
        r"^sortez uniquement.*",
        r"^afficher uniquement.*",
        r"^ne incluez.*",
        r"^vous devez.*",
        r"^il faut.*",
        r"^veuillez.*",
        r"^les éléments suivants.*",
        r"^le nom.*doit être.*",  # Pattern matching form instructions
        r".*code erreur.*",  # Error code patterns
        r".*\(obligatoire\).*",  # Required field patterns
        r".*\(facultative?\).*",  # Optional field patterns
        # English instructions
        r"^output only.*",
        r"^do not include.*",
        r"^you must.*",
        r"^please.*",
        r"^remember\s*[:：].*",
        r"^critical\s*[:：].*",
        r"^important\s*[:：].*",
        r"^instructions?\s*[:：].*",
        r"^traduction\s*[:：]\s*$",
        r"^translation\s*[:：]\s*$",
    ]
    
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            cleaned_lines.append(line)  # Keep empty lines for formatting
            continue
        
        line_lower = line_stripped.lower()
        
        # Check if line matches any instruction pattern
        is_instruction_line = any(re.match(pattern, line_lower, re.IGNORECASE) for pattern in instruction_patterns)
        
        # Also check for lines that are ONLY instruction keywords
        instruction_only_keywords = [
            "n'oubliez pas", "rappel", "remarque", "attention", "note", 
            "important", "critical", "remember", "souviens-toi",
            "instructions", "instruction"
        ]
        is_keyword_only = line_lower in instruction_only_keywords
        
        # Skip instruction lines
        if is_instruction_line or is_keyword_only:
            continue
        
        cleaned_lines.append(line)
    
    text = '\n'.join(cleaned_lines)
    
    # Now handle paragraph-level cleaning for any remaining issues
    paragraphs = text.split('\n\n')
    cleaned_paragraphs = []
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        # If entire paragraph is very short and looks like instruction, skip it
        para_lower = para.lower()
        if len(para) < 50 and any(keyword in para_lower for keyword in ["rappel", "remarque", "n'oubliez", "attention", "note", "sortez"]):
            continue
        
        # Check for hallucination markers (form content, error codes, etc.)
        hallucination_markers = [
            "code erreur", "error code", "obligatoire", "required", "facultative", "optional",
            "formulaire", "form", "saisie", "input", "administrateur", "administrator"
        ]
        if any(marker in para_lower for marker in hallucination_markers):
            # Likely hallucinated content about forms/errors - skip it
            logger.warning(f"Removing likely hallucinated content: '{para[:80]}'")
            continue
        
        cleaned_paragraphs.append(para)
    
    text = '\n\n'.join(cleaned_paragraphs)
    
    # Step 4: Remove standalone bullets/markers (already done in step 3)
    # Just ensure no duplicate processing
    
    # Step 5: Final cleanup
    text = re.sub(r'\n{3,}', '\n\n', text)  # Max 2 consecutive newlines
    text = re.sub(r'\s+$', '', text, flags=re.MULTILINE)  # Remove trailing spaces
    text = text.strip()
    
    was_modified = text != original
    return text, was_modified
