"""Agents module for patcher with LangChain integration."""

from patcher.agents.base import BaseAgent, AgentContext
from patcher.agents.code_agent import CodeAgent, CodeAgentResult
from patcher.agents.review_agent import ReviewAgent, ReviewResult
from patcher.agents.graph_agent import GraphAgent, create_issue_processing_graph
from patcher.agents.tools import (
    create_github_tools,
    create_code_analysis_tools,
    create_all_tools,
)

__all__ = [
    # Base
    "BaseAgent",
    "AgentContext",
    # Code Agent
    "CodeAgent",
    "CodeAgentResult",
    # Review Agent
    "ReviewAgent",
    "ReviewResult",
    # Graph Agent
    "GraphAgent",
    "create_issue_processing_graph",
    # Tools
    "create_github_tools",
    "create_code_analysis_tools",
    "create_all_tools",
]
