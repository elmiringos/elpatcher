"""LLM abstraction layer for patcher using LangChain."""

from patcher.llm.provider import LLMProvider, Message, LLMResponse
from patcher.llm.factory import get_provider, get_model, LLMConfigError
from patcher.llm.schemas import (
    RequirementsAnalysis,
    FileChange,
    ImplementationPlan,
    CodeGeneration,
    ReviewIssue,
    CodeReview,
    CIAnalysis,
)

__all__ = [
    # Provider
    "LLMProvider",
    "Message",
    "LLMResponse",
    # Factory
    "get_provider",
    "get_model",
    "LLMConfigError",
    # Schemas
    "RequirementsAnalysis",
    "FileChange",
    "ImplementationPlan",
    "CodeGeneration",
    "ReviewIssue",
    "CodeReview",
    "CIAnalysis",
]
