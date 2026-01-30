"""Prompt templates and few-shot examples for patcher agents."""

from patcher.prompts.few_shots import (
    CODE_GENERATION_EXAMPLES,
    CODE_FIX_EXAMPLES,
    CI_FIX_EXAMPLES,
    REVIEW_EXAMPLES,
    format_code_generation_examples,
    format_code_fix_examples,
    format_ci_fix_examples,
    format_review_examples,
)
from patcher.prompts.templates import (
    CODE_GENERATION_PROMPT,
    CODE_FIX_PROMPT,
    CI_ANALYSIS_PROMPT,
    REVIEW_PROMPT,
)

__all__ = [
    "CODE_GENERATION_EXAMPLES",
    "CODE_FIX_EXAMPLES",
    "CI_FIX_EXAMPLES",
    "REVIEW_EXAMPLES",
    "format_code_generation_examples",
    "format_code_fix_examples",
    "format_ci_fix_examples",
    "format_review_examples",
    "CODE_GENERATION_PROMPT",
    "CODE_FIX_PROMPT",
    "CI_ANALYSIS_PROMPT",
    "REVIEW_PROMPT",
]
