"""Unit tests for GitHub client."""

import pytest
from unittest.mock import MagicMock, patch

from patcher.github.client import GitHubClient, GitHubClientError
from patcher.github.models import CIStatus


class TestGitHubClientInit:
    """Tests for GitHubClient initialization."""

    def test_init_without_token_raises_error(self):
        """Test that missing token raises error."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(GitHubClientError, match="GitHub token"):
                GitHubClient()

    def test_init_with_token(self):
        """Test initialization with token."""
        client = GitHubClient(token="test-token", repo_name="owner/repo")
        assert client.token == "test-token"
        assert client._repo_name == "owner/repo"

    def test_init_from_env(self):
        """Test initialization from environment."""
        with patch.dict("os.environ", {"GITHUB_TOKEN": "env-token"}):
            client = GitHubClient()
            assert client.token == "env-token"


class TestGitHubClientURLParsing:
    """Tests for URL parsing methods."""

    def test_parse_issue_url(self):
        """Test parsing GitHub issue URL."""
        url = "https://github.com/owner/repo/issues/42"
        repo, number = GitHubClient.parse_issue_url(url)
        assert repo == "owner/repo"
        assert number == 42

    def test_parse_issue_url_with_params(self):
        """Test parsing issue URL with query params."""
        url = "https://github.com/owner/repo/issues/42?some=param"
        repo, number = GitHubClient.parse_issue_url(url)
        assert repo == "owner/repo"
        assert number == 42

    def test_parse_invalid_issue_url(self):
        """Test that invalid URL raises error."""
        with pytest.raises(GitHubClientError, match="Invalid GitHub issue URL"):
            GitHubClient.parse_issue_url("https://example.com/issues/42")

    def test_parse_pr_url(self):
        """Test parsing GitHub PR URL."""
        url = "https://github.com/owner/repo/pull/123"
        repo, number = GitHubClient.parse_pr_url(url)
        assert repo == "owner/repo"
        assert number == 123

    def test_parse_invalid_pr_url(self):
        """Test that invalid PR URL raises error."""
        with pytest.raises(GitHubClientError, match="Invalid GitHub PR URL"):
            GitHubClient.parse_pr_url("https://example.com/pull/123")


class TestGitHubClientRepo:
    """Tests for repository operations."""

    def test_repo_property_without_name(self):
        """Test accessing repo without name set."""
        client = GitHubClient(token="test-token")
        with pytest.raises(GitHubClientError, match="Repository name not set"):
            _ = client.repo

    def test_set_repo(self):
        """Test setting repository name."""
        client = GitHubClient(token="test-token")
        client.set_repo("owner/repo")
        assert client._repo_name == "owner/repo"
        assert client._repo is None  # Should be reset


class TestGitHubClientIssue:
    """Tests for issue operations."""

    def test_get_issue(self):
        """Test fetching issue details."""
        client = GitHubClient(token="test-token", repo_name="owner/repo")

        # Mock the GitHub client
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_issue.number = 42
        mock_issue.title = "Test Issue"
        mock_issue.body = "Issue body"
        mock_issue.labels = [MagicMock(name="bug"), MagicMock(name="ai-agent")]
        mock_issue.state = "open"
        mock_issue.html_url = "https://github.com/owner/repo/issues/42"
        mock_issue.created_at = None
        mock_issue.updated_at = None
        mock_repo.get_issue.return_value = mock_issue

        client._repo = mock_repo

        issue = client.get_issue(42)

        assert issue.number == 42
        assert issue.title == "Test Issue"
        assert issue.body == "Issue body"
        assert "bug" in issue.labels
        assert "ai-agent" in issue.labels


class TestGitHubClientPR:
    """Tests for PR operations."""

    def test_get_pr(self):
        """Test fetching PR details."""
        client = GitHubClient(token="test-token", repo_name="owner/repo")

        # Mock the GitHub client
        mock_repo = MagicMock()
        mock_pr = MagicMock()
        mock_pr.number = 123
        mock_pr.title = "Test PR"
        mock_pr.body = "PR body"
        mock_pr.head.ref = "feature/test"
        mock_pr.base.ref = "main"
        mock_pr.labels = [MagicMock(name="ai-generated")]
        mock_pr.state = "open"
        mock_pr.html_url = "https://github.com/owner/repo/pull/123"
        mock_pr.mergeable = True
        mock_pr.draft = False
        mock_pr.created_at = None
        mock_pr.updated_at = None
        mock_repo.get_pull.return_value = mock_pr

        client._repo = mock_repo

        pr = client.get_pr(123)

        assert pr.number == 123
        assert pr.title == "Test PR"
        assert pr.head_branch == "feature/test"
        assert pr.base_branch == "main"
        assert "ai-generated" in pr.labels


class TestGitHubClientCI:
    """Tests for CI status operations."""

    def test_get_ci_status_all_passed(self):
        """Test getting CI status when all checks pass."""
        client = GitHubClient(token="test-token", repo_name="owner/repo")

        mock_repo = MagicMock()
        mock_pr = MagicMock()
        mock_commit = MagicMock()

        # Create mock check runs
        mock_check1 = MagicMock()
        mock_check1.name = "lint"
        mock_check1.status = "completed"
        mock_check1.conclusion = "success"
        mock_check1.html_url = "https://example.com/check1"
        mock_check1.output = {"summary": "All good"}

        mock_check2 = MagicMock()
        mock_check2.name = "test"
        mock_check2.status = "completed"
        mock_check2.conclusion = "success"
        mock_check2.html_url = "https://example.com/check2"
        mock_check2.output = {"summary": "Tests passed"}

        mock_commit.get_check_runs.return_value = [mock_check1, mock_check2]
        mock_pr.get_commits.return_value.reversed = [mock_commit]
        mock_repo.get_pull.return_value = mock_pr

        client._repo = mock_repo

        result = client.get_ci_status(123)

        assert result.status == CIStatus.SUCCESS
        assert len(result.checks) == 2
        assert all(c.status == CIStatus.SUCCESS for c in result.checks)

    def test_get_ci_status_with_failure(self):
        """Test getting CI status with a failed check."""
        client = GitHubClient(token="test-token", repo_name="owner/repo")

        mock_repo = MagicMock()
        mock_pr = MagicMock()
        mock_commit = MagicMock()

        mock_check = MagicMock()
        mock_check.name = "test"
        mock_check.status = "completed"
        mock_check.conclusion = "failure"
        mock_check.html_url = "https://example.com/check"
        mock_check.output = {"summary": "Tests failed"}

        mock_commit.get_check_runs.return_value = [mock_check]
        mock_pr.get_commits.return_value.reversed = [mock_commit]
        mock_repo.get_pull.return_value = mock_pr

        client._repo = mock_repo

        result = client.get_ci_status(123)

        assert result.status == CIStatus.FAILURE
        assert result.checks[0].status == CIStatus.FAILURE
