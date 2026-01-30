"""GitHub integration module for patcher."""

from patcher.github.client import GitHubClient, GitHubClientError
from patcher.github.models import (
    IssueData,
    PRData,
    FileChange,
    CIResult,
    CICheck,
    CIStatus,
    ReviewComment,
)

__all__ = [
    "GitHubClient",
    "GitHubClientError",
    "IssueData",
    "PRData",
    "FileChange",
    "CIResult",
    "CICheck",
    "CIStatus",
    "ReviewComment",
]
