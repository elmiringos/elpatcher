"""Integration tests for Review Agent with LangChain."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from patcher.agents.review_agent import ReviewAgent
from patcher.agents.base import AgentContext
from patcher.github.models import PRData, IssueData, CIResult, CIStatus, CICheck
from patcher.llm.provider import LLMProvider
from patcher.llm.schemas import CodeReview, ReviewIssue, CIAnalysis as CIAnalysisSchema


@pytest.fixture
def mock_llm_model():
    """Create a mock LangChain model."""
    model = MagicMock()
    model.ainvoke = AsyncMock()
    model.with_structured_output = MagicMock(return_value=model)
    return model


@pytest.fixture
def mock_llm_provider(mock_llm_model):
    """Create a mock LLM provider."""
    return LLMProvider(model=mock_llm_model, model_name="test-model")


@pytest.fixture
def mock_github_client():
    """Create a mock GitHub client."""
    client = MagicMock()
    client.repo = MagicMock()
    return client


@pytest.fixture
def mock_context(mock_github_client, mock_llm_provider):
    """Create a mock agent context."""
    return AgentContext(
        github_client=mock_github_client,
        llm_provider=mock_llm_provider,
    )


@pytest.fixture
def sample_pr():
    """Create a sample PR."""
    return PRData(
        number=123,
        title="feat: Add greeting function",
        body="""## Summary
Adds a greeting function.

Resolves #42""",
        head_branch="patcher/issue-42-greeting",
        base_branch="main",
        labels=["ai-generated"],
        url="https://github.com/owner/repo/pull/123",
    )


@pytest.fixture
def sample_issue():
    """Create a sample issue."""
    return IssueData(
        number=42,
        title="Add greeting function",
        body="Add a function that returns Hello World",
        labels=["ai-agent"],
    )


@pytest.fixture
def sample_ci_success():
    """Create successful CI result."""
    return CIResult(
        status=CIStatus.SUCCESS,
        checks=[
            CICheck(name="lint", status=CIStatus.SUCCESS, conclusion="success"),
            CICheck(name="test", status=CIStatus.SUCCESS, conclusion="success"),
        ],
    )


@pytest.fixture
def sample_ci_failure():
    """Create failed CI result."""
    return CIResult(
        status=CIStatus.FAILURE,
        checks=[
            CICheck(name="lint", status=CIStatus.SUCCESS, conclusion="success"),
            CICheck(
                name="test",
                status=CIStatus.FAILURE,
                conclusion="failure",
                output="AssertionError: Test failed",
            ),
        ],
    )


@pytest.fixture
def sample_approved_review():
    """Create an approved code review."""
    return CodeReview(
        assessment="The implementation looks good",
        issues=[],
        requirements_met=True,
        requirements_notes="All requirements implemented",
        approved=True,
    )


@pytest.fixture
def sample_rejected_review():
    """Create a rejected code review."""
    return CodeReview(
        assessment="Has some issues",
        issues=[
            ReviewIssue(
                severity="error",
                file_path="src/greet.py",
                line=10,
                description="Missing null check",
                suggestion="Add if name is None check",
            ),
        ],
        requirements_met=False,
        requirements_notes="Missing greeting for empty name",
        approved=False,
    )


class TestReviewAgentIssueExtraction:
    """Tests for issue extraction from PR."""

    def test_extract_issue_resolves(self, mock_context, sample_pr, sample_issue):
        """Test extracting issue from 'Resolves #N' pattern."""
        mock_context.github_client.get_issue.return_value = sample_issue

        agent = ReviewAgent(mock_context)
        issue = agent._extract_issue_from_pr(sample_pr)

        assert issue is not None
        assert issue.number == 42

    def test_extract_issue_fixes(self, mock_context):
        """Test extracting issue from 'Fixes #N' pattern."""
        pr = PRData(
            number=1,
            title="Fix bug",
            body="Fixes #99",
            head_branch="fix",
            base_branch="main",
        )
        mock_context.github_client.get_issue.return_value = IssueData(
            number=99,
            title="Bug",
            body="Fix it",
        )

        agent = ReviewAgent(mock_context)
        issue = agent._extract_issue_from_pr(pr)

        assert issue is not None
        assert issue.number == 99

    def test_extract_issue_none(self, mock_context):
        """Test when no issue reference found."""
        pr = PRData(
            number=1,
            title="Some PR",
            body="No issue reference here",
            head_branch="feature",
            base_branch="main",
        )

        agent = ReviewAgent(mock_context)
        issue = agent._extract_issue_from_pr(pr)

        assert issue is None


class TestReviewAgentCIAnalysis:
    """Tests for CI analysis."""

    @pytest.mark.asyncio
    async def test_analyze_ci_success(self, mock_context, sample_ci_success):
        """Test analyzing successful CI."""
        agent = ReviewAgent(mock_context)
        analysis = await agent._analyze_ci(sample_ci_success)

        assert analysis.passed is True
        assert "passed" in analysis.summary.lower()
        assert len(analysis.failures) == 0

    @pytest.mark.asyncio
    async def test_analyze_ci_failure(self, mock_context, sample_ci_failure):
        """Test analyzing failed CI."""
        # Mock the CI analysis chain
        ci_analysis = CIAnalysisSchema(
            passed=False,
            failures=["test: AssertionError"],
            root_causes=["Assertion failed in test"],
            suggested_fixes=["Fix the assertion"],
        )
        mock_context.llm_provider.model.with_structured_output.return_value.ainvoke = (
            AsyncMock(return_value=ci_analysis)
        )

        agent = ReviewAgent(mock_context)
        analysis = await agent._analyze_ci(sample_ci_failure)

        assert analysis.passed is False
        assert len(analysis.failures) > 0


class TestReviewAgentFullWorkflow:
    """Tests for full review workflow."""

    @pytest.mark.asyncio
    async def test_review_approved(
        self,
        mock_context,
        sample_pr,
        sample_issue,
        sample_ci_success,
        sample_approved_review,
    ):
        """Test review that approves PR."""
        # Set up mocks
        mock_context.github_client.get_pr.return_value = sample_pr
        mock_context.github_client.get_pr_diff.return_value = "diff content"
        mock_context.github_client.get_issue.return_value = sample_issue
        mock_context.github_client.get_ci_status.return_value = sample_ci_success

        # Mock chains
        mock_chain = AsyncMock()
        mock_chain.ainvoke = AsyncMock(return_value=sample_approved_review)

        agent = ReviewAgent(mock_context)
        agent._review_chain = mock_chain

        result = await agent.run(
            pr_number=123,
            issue_number=42,
            check_ci=True,
            post_review=False,
        )

        assert result.approved is True
        assert "Requirements met" in result.summary

    @pytest.mark.asyncio
    async def test_review_requests_changes(
        self,
        mock_context,
        sample_pr,
        sample_issue,
        sample_ci_success,
        sample_rejected_review,
    ):
        """Test review that requests changes."""
        # Set up mocks
        mock_context.github_client.get_pr.return_value = sample_pr
        mock_context.github_client.get_pr_diff.return_value = "diff content"
        mock_context.github_client.get_issue.return_value = sample_issue
        mock_context.github_client.get_ci_status.return_value = sample_ci_success

        # Mock chains
        mock_chain = AsyncMock()
        mock_chain.ainvoke = AsyncMock(return_value=sample_rejected_review)

        agent = ReviewAgent(mock_context)
        agent._review_chain = mock_chain

        result = await agent.run(
            pr_number=123,
            issue_number=42,
            check_ci=True,
            post_review=False,
        )

        assert result.approved is False
        assert len(result.suggestions) > 0

    @pytest.mark.asyncio
    async def test_review_posts_comments(
        self,
        mock_context,
        sample_pr,
        sample_issue,
        sample_ci_success,
        sample_approved_review,
    ):
        """Test that review posts comments to PR."""
        # Set up mocks
        mock_context.github_client.get_pr.return_value = sample_pr
        mock_context.github_client.get_pr_diff.return_value = "diff"
        mock_context.github_client.get_issue.return_value = sample_issue
        mock_context.github_client.get_ci_status.return_value = sample_ci_success

        mock_chain = AsyncMock()
        mock_chain.ainvoke = AsyncMock(return_value=sample_approved_review)

        agent = ReviewAgent(mock_context)
        agent._review_chain = mock_chain

        await agent.run(
            pr_number=123,
            issue_number=42,
            check_ci=True,
            post_review=True,
        )

        mock_context.github_client.post_review.assert_called_once()
        call_kwargs = mock_context.github_client.post_review.call_args.kwargs
        assert call_kwargs["pr_number"] == 123
        assert call_kwargs["event"] == "APPROVE"


class TestReviewAgentSummaryBuilding:
    """Tests for summary building."""

    def test_build_summary_approved(
        self, mock_context, sample_approved_review
    ):
        """Test building summary for approved review."""
        from patcher.agents.review_agent import CIAnalysis

        agent = ReviewAgent(mock_context)
        ci = CIAnalysis(passed=True, summary="All passed")

        summary = agent._build_summary(sample_approved_review, ci)

        assert "Assessment" in summary
        assert "Requirements met" in summary
        assert "CI checks passed" in summary
        assert "Approved" in summary

    def test_build_summary_with_issues(
        self, mock_context, sample_rejected_review
    ):
        """Test building summary with issues."""
        from patcher.agents.review_agent import CIAnalysis

        agent = ReviewAgent(mock_context)
        ci = CIAnalysis(passed=True, summary="All passed")

        summary = agent._build_summary(sample_rejected_review, ci)

        assert "error" in summary.lower()
        assert "Changes requested" in summary
