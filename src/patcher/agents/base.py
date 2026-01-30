"""Base agent class."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import logging
from typing import Any

from patcher.github.client import GitHubClient
from patcher.llm.provider import LLMProvider


@dataclass
class AgentContext:
    """Context passed to agents for processing."""

    github_client: GitHubClient
    llm_provider: LLMProvider
    max_iterations: int = 5
    current_iteration: int = 0
    base_branch: str = "main"
    workspace_path: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class BaseAgent(ABC):
    """Base class for all agents."""

    def __init__(self, context: AgentContext):
        """Initialize the agent.

        Args:
            context: Agent context with clients and configuration
        """
        self.context = context
        self.logger = logging.getLogger(self.__class__.__name__)

    @property
    def github(self) -> GitHubClient:
        """Get the GitHub client."""
        return self.context.github_client

    @property
    def llm(self) -> LLMProvider:
        """Get the LLM provider."""
        return self.context.llm_provider

    @abstractmethod
    async def run(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the agent's main task.

        Args:
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Agent-specific result
        """
        pass

    def _log_info(self, message: str) -> None:
        """Log an info message."""
        self.logger.info(message)

    def _log_error(self, message: str) -> None:
        """Log an error message."""
        self.logger.error(message)

    def _log_warning(self, message: str) -> None:
        """Log a warning message."""
        self.logger.warning(message)

    def _log_debug(self, message: str) -> None:
        """Log a debug message."""
        self.logger.debug(message)
