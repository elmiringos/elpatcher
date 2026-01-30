"""Unit tests for state management."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from patcher.state.models import AgentState, Iteration, IterationStatus
from patcher.state.manager import StateManager, STATE_MARKER_START, STATE_MARKER_END


class TestIterationStatus:
    """Tests for IterationStatus enum."""

    def test_all_statuses(self):
        """Test all status values exist."""
        assert IterationStatus.PENDING == "pending"
        assert IterationStatus.IN_PROGRESS == "in_progress"
        assert IterationStatus.AWAITING_REVIEW == "awaiting_review"
        assert IterationStatus.NEEDS_CHANGES == "needs_changes"
        assert IterationStatus.COMPLETED == "completed"
        assert IterationStatus.FAILED == "failed"


class TestIteration:
    """Tests for Iteration dataclass."""

    def test_create_iteration(self):
        """Test creating an iteration."""
        iteration = Iteration(
            number=1,
            status=IterationStatus.PENDING,
            changes=["file1.py", "file2.py"],
        )
        assert iteration.number == 1
        assert iteration.status == IterationStatus.PENDING
        assert iteration.changes == ["file1.py", "file2.py"]
        assert iteration.review_feedback is None
        assert iteration.ci_status is None

    def test_iteration_defaults(self):
        """Test iteration default values."""
        iteration = Iteration(number=1, status=IterationStatus.PENDING)
        assert iteration.changes == []
        assert isinstance(iteration.timestamp, datetime)


class TestAgentState:
    """Tests for AgentState dataclass."""

    def test_create_state(self):
        """Test creating agent state."""
        state = AgentState(issue_number=42)
        assert state.issue_number == 42
        assert state.pr_number is None
        assert state.iterations == []
        assert state.iteration_count == 0

    def test_add_iteration(self):
        """Test adding iterations."""
        state = AgentState(issue_number=42)

        iteration1 = state.add_iteration(
            status=IterationStatus.IN_PROGRESS,
            changes=["file1.py"],
        )
        assert iteration1.number == 1
        assert state.iteration_count == 1
        assert state.current_iteration == iteration1

        iteration2 = state.add_iteration(status=IterationStatus.PENDING)
        assert iteration2.number == 2
        assert state.iteration_count == 2
        assert state.current_iteration == iteration2

    def test_current_iteration_empty(self):
        """Test current_iteration when no iterations."""
        state = AgentState(issue_number=42)
        assert state.current_iteration is None

    def test_to_dict(self):
        """Test serialization to dictionary."""
        state = AgentState(
            issue_number=42,
            pr_number=123,
            branch_name="feature/test",
            requirements_hash="abc123",
        )
        state.add_iteration(
            status=IterationStatus.COMPLETED,
            changes=["file.py"],
        )

        data = state.to_dict()

        assert data["issue_number"] == 42
        assert data["pr_number"] == 123
        assert data["branch_name"] == "feature/test"
        assert data["requirements_hash"] == "abc123"
        assert len(data["iterations"]) == 1
        assert data["iterations"][0]["number"] == 1
        assert data["iterations"][0]["status"] == "completed"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "issue_number": 42,
            "pr_number": 123,
            "branch_name": "feature/test",
            "requirements_hash": "abc123",
            "iterations": [
                {
                    "number": 1,
                    "status": "completed",
                    "changes": ["file.py"],
                    "review_feedback": "Looks good",
                    "ci_status": "passed",
                    "commit_sha": "abc",
                    "timestamp": "2024-01-01T00:00:00",
                }
            ],
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
        }

        state = AgentState.from_dict(data)

        assert state.issue_number == 42
        assert state.pr_number == 123
        assert state.branch_name == "feature/test"
        assert state.iteration_count == 1
        assert state.current_iteration.status == IterationStatus.COMPLETED
        assert state.current_iteration.review_feedback == "Looks good"


class TestStateManager:
    """Tests for StateManager."""

    def test_format_state_for_pr(self):
        """Test formatting state as HTML comment."""
        state = AgentState(issue_number=42, pr_number=123)
        state.add_iteration(status=IterationStatus.PENDING)

        formatted = StateManager.format_state_for_pr(state)

        assert STATE_MARKER_START in formatted
        assert STATE_MARKER_END in formatted
        assert '"issue_number": 42' in formatted

    def test_extract_visible_body(self):
        """Test extracting visible body without state."""
        body = """This is the PR description.

Some more content.

<!-- PATCHER_STATE_START
{"issue_number": 42}
PATCHER_STATE_END -->"""

        visible = StateManager.extract_visible_body(body)

        assert "This is the PR description" in visible
        assert "Some more content" in visible
        assert "PATCHER_STATE" not in visible
        assert "issue_number" not in visible

    def test_save_and_load_state(self):
        """Test saving and loading state from PR."""
        # Create mock GitHub client
        mock_github = MagicMock()
        mock_pr = MagicMock()
        mock_pr.body = "Original PR body"
        mock_github.get_pr.return_value = mock_pr

        manager = StateManager(mock_github)

        # Create state
        state = AgentState(issue_number=42, pr_number=123)
        state.add_iteration(status=IterationStatus.AWAITING_REVIEW)

        # Save state
        manager.save_to_pr(123, state)

        # Verify update was called
        mock_github.update_pr.assert_called_once()
        call_kwargs = mock_github.update_pr.call_args.kwargs
        assert "body" in call_kwargs
        assert STATE_MARKER_START in call_kwargs["body"]

    def test_load_nonexistent_state(self):
        """Test loading state when none exists."""
        mock_github = MagicMock()
        mock_pr = MagicMock()
        mock_pr.body = "PR without state"
        mock_github.get_pr.return_value = mock_pr

        manager = StateManager(mock_github)
        state = manager.load_from_pr(123)

        assert state is None

    def test_load_existing_state(self):
        """Test loading existing state from PR."""
        mock_github = MagicMock()
        mock_pr = MagicMock()
        mock_pr.body = """PR description

<!-- PATCHER_STATE_START
{
  "issue_number": 42,
  "pr_number": 123,
  "branch_name": "test",
  "iterations": [],
  "requirements_hash": "",
  "created_at": "2024-01-01T00:00:00",
  "updated_at": "2024-01-01T00:00:00"
}
PATCHER_STATE_END -->"""
        mock_github.get_pr.return_value = mock_pr

        manager = StateManager(mock_github)
        state = manager.load_from_pr(123)

        assert state is not None
        assert state.issue_number == 42
        assert state.pr_number == 123
