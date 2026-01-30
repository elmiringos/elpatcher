"""Integration tests for Code Agent with LangChain."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from patcher.agents.code_agent import CodeAgent
from patcher.agents.base import AgentContext
from patcher.github.models import IssueData
from patcher.llm.provider import LLMProvider
from patcher.llm.schemas import RequirementsAnalysis, ImplementationPlan, CodeGeneration, FileChange


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
    provider = LLMProvider(model=mock_llm_model, model_name="test-model")
    return provider


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
        max_iterations=5,
        base_branch="main",
    )


@pytest.fixture
def sample_issue():
    """Create a sample issue."""
    return IssueData(
        number=42,
        title="Add greeting function",
        body="""## Requirements
- Add a function that returns "Hello, World!"
- Add tests for the function""",
        labels=["ai-agent", "feature"],
        url="https://github.com/owner/repo/issues/42",
    )


@pytest.fixture
def sample_requirements():
    """Create sample requirements analysis."""
    return RequirementsAnalysis(
        summary="Add a greeting function with tests",
        tasks=["Create greet() function", "Add unit tests"],
        files_to_modify=["src/utils.py"],
        files_to_create=["tests/test_utils.py"],
        test_requirements=["Test default greeting", "Test custom name"],
        dependencies=[],
    )


@pytest.fixture
def sample_plan():
    """Create sample implementation plan."""
    return ImplementationPlan(
        approach="Create a simple greeting function",
        steps=["Create function", "Add tests", "Update exports"],
        risks=["None significant"],
        testing_strategy="Unit tests with pytest",
    )


@pytest.fixture
def sample_code_gen():
    """Create sample code generation."""
    return CodeGeneration(
        files=[
            FileChange(
                path="src/greet.py",
                content='def greet(name="World"):\n    return f"Hello, {name}!"',
                action="create",
            ),
            FileChange(
                path="tests/test_greet.py",
                content='def test_greet():\n    assert greet() == "Hello, World!"',
                action="create",
            ),
        ],
        explanation="Created greeting function with tests",
    )


class TestCodeAgentWithLangChain:
    """Tests for Code Agent with LangChain integration."""

    @pytest.mark.asyncio
    async def test_analyze_requirements(
        self, mock_context, sample_issue, sample_requirements
    ):
        """Test requirements extraction using structured output."""
        # Mock the structured chain
        mock_context.llm_provider.model.with_structured_output.return_value.ainvoke = (
            AsyncMock(return_value=sample_requirements)
        )

        agent = CodeAgent(mock_context)

        # Call the chain directly
        result = await agent._requirements_chain.ainvoke({
            "messages": [MagicMock(content="Analyze this issue")]
        })

        # The result should be structured
        assert result == sample_requirements

    @pytest.mark.asyncio
    async def test_generate_plan(
        self, mock_context, sample_issue, sample_requirements, sample_plan
    ):
        """Test plan generation using structured output."""
        mock_context.llm_provider.model.with_structured_output.return_value.ainvoke = (
            AsyncMock(return_value=sample_plan)
        )

        agent = CodeAgent(mock_context)
        result = await agent._plan_chain.ainvoke({
            "messages": [MagicMock(content="Create plan")]
        })

        assert result.approach == sample_plan.approach
        assert len(result.steps) == len(sample_plan.steps)

    @pytest.mark.asyncio
    async def test_generate_code(
        self, mock_context, sample_code_gen
    ):
        """Test code generation using structured output."""
        mock_context.llm_provider.model.with_structured_output.return_value.ainvoke = (
            AsyncMock(return_value=sample_code_gen)
        )

        agent = CodeAgent(mock_context)
        result = await agent._code_chain.ainvoke({
            "messages": [MagicMock(content="Generate code")]
        })

        assert len(result.files) == 2
        assert result.files[0].path == "src/greet.py"
        assert result.files[0].action == "create"

    @pytest.mark.asyncio
    async def test_run_dry_run(
        self,
        mock_context,
        sample_issue,
        sample_requirements,
        sample_plan,
        sample_code_gen,
    ):
        """Test running agent in dry-run mode."""
        # Set up mocks
        mock_context.github_client.get_issue.return_value = sample_issue
        mock_context.github_client.get_file_content.side_effect = Exception("Not found")

        # Set up chain responses
        mock_chain = AsyncMock()
        mock_chain.ainvoke = AsyncMock(
            side_effect=[sample_requirements, sample_plan, sample_code_gen]
        )
        mock_context.llm_provider.model.with_structured_output.return_value = mock_chain

        agent = CodeAgent(mock_context)

        # Override chains with mocked versions
        agent._requirements_chain = mock_chain
        agent._plan_chain = mock_chain
        agent._code_chain = mock_chain

        result = await agent.run(issue_number=42, dry_run=True)

        assert result.success is True
        assert result.pr_url is None  # Dry run, no PR
        assert result.changes is not None
        assert len(result.changes) == 2

    @pytest.mark.asyncio
    async def test_run_creates_pr(
        self,
        mock_context,
        sample_issue,
        sample_requirements,
        sample_plan,
        sample_code_gen,
    ):
        """Test running agent creates PR."""
        # Set up mocks
        mock_context.github_client.get_issue.return_value = sample_issue
        mock_context.github_client.get_file_content.side_effect = Exception("Not found")
        mock_context.github_client.create_branch.return_value = None
        mock_context.github_client.commit_changes.return_value = "abc123"

        mock_pr = MagicMock()
        mock_pr.number = 123
        mock_pr.url = "https://github.com/owner/repo/pull/123"
        mock_context.github_client.create_pull_request.return_value = mock_pr
        mock_context.github_client.update_pr.return_value = mock_pr
        mock_context.github_client.get_pr.return_value = MagicMock(
            body="PR body",
            number=123,
        )

        # Set up chain responses
        mock_chain = AsyncMock()
        mock_chain.ainvoke = AsyncMock(
            side_effect=[sample_requirements, sample_plan, sample_code_gen]
        )

        agent = CodeAgent(mock_context)
        agent._requirements_chain = mock_chain
        agent._plan_chain = mock_chain
        agent._code_chain = mock_chain

        result = await agent.run(issue_number=42, dry_run=False)

        assert result.success is True
        assert result.pr_url is not None
        mock_context.github_client.create_branch.assert_called_once()
        mock_context.github_client.commit_changes.assert_called_once()
        mock_context.github_client.create_pull_request.assert_called_once()


class TestCodeAgentBranchNaming:
    """Tests for branch name generation."""

    def test_generate_branch_name(self, mock_context, sample_issue):
        """Test branch name generation."""
        agent = CodeAgent(mock_context)
        branch = agent._generate_branch_name(sample_issue)

        assert branch.startswith("patcher/issue-42-")
        assert "greeting" in branch.lower()
        assert len(branch) <= 60

    def test_generate_branch_name_long_title(self, mock_context):
        """Test branch name with long title is truncated."""
        long_issue = IssueData(
            number=1,
            title="This is a very long issue title that should be truncated for branch name",
            body="Body",
        )
        agent = CodeAgent(mock_context)
        branch = agent._generate_branch_name(long_issue)

        assert len(branch) <= 60
        assert branch.startswith("patcher/issue-1-")

    def test_hash_requirements(self, mock_context):
        """Test requirements hashing."""
        agent = CodeAgent(mock_context)

        hash1 = agent._hash_requirements("Test body")
        hash2 = agent._hash_requirements("Test body")
        hash3 = agent._hash_requirements("Different body")

        assert hash1 == hash2
        assert hash1 != hash3
        assert len(hash1) == 16
