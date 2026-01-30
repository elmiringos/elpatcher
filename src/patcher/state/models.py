"""Data models for agent state management."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class IterationStatus(str, Enum):
    """Status of an iteration."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    AWAITING_REVIEW = "awaiting_review"
    NEEDS_CHANGES = "needs_changes"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Iteration:
    """A single iteration of the agent loop."""

    number: int
    status: IterationStatus
    changes: list[str] = field(default_factory=list)  # File paths changed
    review_feedback: str | None = None
    ci_status: str | None = None
    commit_sha: str | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AgentState:
    """State of an agent across iterations."""

    issue_number: int
    pr_number: int | None = None
    branch_name: str = ""
    iterations: list[Iteration] = field(default_factory=list)
    requirements_hash: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def add_iteration(
        self,
        status: IterationStatus = IterationStatus.PENDING,
        changes: list[str] | None = None,
    ) -> Iteration:
        """Add a new iteration to the state.

        Args:
            status: Initial status of the iteration
            changes: List of file paths changed

        Returns:
            The new Iteration object
        """
        iteration = Iteration(
            number=len(self.iterations) + 1,
            status=status,
            changes=changes or [],
        )
        self.iterations.append(iteration)
        self.updated_at = datetime.utcnow()
        return iteration

    @property
    def current_iteration(self) -> Iteration | None:
        """Get the current (latest) iteration."""
        return self.iterations[-1] if self.iterations else None

    @property
    def iteration_count(self) -> int:
        """Get the number of iterations."""
        return len(self.iterations)

    def to_dict(self) -> dict:
        """Convert state to dictionary for serialization."""
        return {
            "issue_number": self.issue_number,
            "pr_number": self.pr_number,
            "branch_name": self.branch_name,
            "iterations": [
                {
                    "number": it.number,
                    "status": it.status.value,
                    "changes": it.changes,
                    "review_feedback": it.review_feedback,
                    "ci_status": it.ci_status,
                    "commit_sha": it.commit_sha,
                    "timestamp": it.timestamp.isoformat(),
                }
                for it in self.iterations
            ],
            "requirements_hash": self.requirements_hash,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentState":
        """Create state from dictionary.

        Args:
            data: Dictionary with state data

        Returns:
            AgentState instance
        """
        state = cls(
            issue_number=data["issue_number"],
            pr_number=data.get("pr_number"),
            branch_name=data.get("branch_name", ""),
            requirements_hash=data.get("requirements_hash", ""),
        )

        if "created_at" in data:
            state.created_at = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data:
            state.updated_at = datetime.fromisoformat(data["updated_at"])

        for it_data in data.get("iterations", []):
            iteration = Iteration(
                number=it_data["number"],
                status=IterationStatus(it_data["status"]),
                changes=it_data.get("changes", []),
                review_feedback=it_data.get("review_feedback"),
                ci_status=it_data.get("ci_status"),
                commit_sha=it_data.get("commit_sha"),
            )
            if "timestamp" in it_data:
                iteration.timestamp = datetime.fromisoformat(it_data["timestamp"])
            state.iterations.append(iteration)

        return state
