"""Data models for GitHub entities."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class CIStatus(str, Enum):
    """CI check status."""

    PENDING = "pending"
    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class IssueData:
    """GitHub Issue data."""

    number: int
    title: str
    body: str
    labels: list[str] = field(default_factory=list)
    state: str = "open"
    url: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class PRData:
    """GitHub Pull Request data."""

    number: int
    title: str
    body: str
    head_branch: str
    base_branch: str
    labels: list[str] = field(default_factory=list)
    state: str = "open"
    url: str = ""
    mergeable: bool | None = None
    draft: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class FileChange:
    """A file change in a commit or PR."""

    path: str
    content: str
    status: str = "modified"  # "added", "modified", "deleted"


@dataclass
class CICheck:
    """A CI check result."""

    name: str
    status: CIStatus
    conclusion: str | None = None
    url: str | None = None
    output: str | None = None


@dataclass
class CIResult:
    """Overall CI result for a PR."""

    status: CIStatus
    checks: list[CICheck] = field(default_factory=list)


@dataclass
class ReviewComment:
    """A review comment on a PR."""

    body: str
    path: str | None = None
    line: int | None = None
    commit_id: str | None = None
