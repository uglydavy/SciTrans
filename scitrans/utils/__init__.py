"""Utility functions for SciTrans."""

from scitrans.utils.backend_checker import (
    check_backend_dependencies,
    get_all_backends_status,
    validate_backend_before_use,
)
from scitrans.utils.env_loader import load_environment_variables
from scitrans.utils.error_recovery import (
    retry_with_backoff,
    retry_with_circuit_breaker,
    safe_call,
)
from scitrans.utils.language_detection import (
    detect_language,
    detect_language_from_pdf,
    get_language_name,
    is_language_code_valid,
)
from scitrans.utils.line_break_preserver import preserve_line_breaks, preserve_paragraph_spacing
from scitrans.utils.numbering_detector import NumberingDetector

__all__ = [
    "check_backend_dependencies",
    "get_all_backends_status",
    "validate_backend_before_use",
    "load_environment_variables",
    "retry_with_backoff",
    "retry_with_circuit_breaker",
    "safe_call",
    "detect_language",
    "detect_language_from_pdf",
    "get_language_name",
    "is_language_code_valid",
    "preserve_line_breaks",
    "preserve_paragraph_spacing",
    "NumberingDetector",
]
