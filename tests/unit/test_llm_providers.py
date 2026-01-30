"""Unit tests for LLM providers with LangChain."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from patcher.llm.provider import Message, LLMResponse, LLMProvider
from patcher.llm.factory import get_provider, get_model, LLMConfigError
from patcher.llm.schemas import RequirementsAnalysis, CodeReview


class TestMessage:
    """Tests for Message dataclass."""

    def test_create_message(self):
        """Test creating a message."""
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_message_roles(self):
        """Test different message roles."""
        for role in ["system", "user", "assistant"]:
            msg = Message(role=role, content="test")
            assert msg.role == role

    def test_to_langchain_system(self):
        """Test converting system message to LangChain format."""
        from langchain_core.messages import SystemMessage

        msg = Message(role="system", content="You are helpful")
        lc_msg = msg.to_langchain()
        assert isinstance(lc_msg, SystemMessage)
        assert lc_msg.content == "You are helpful"

    def test_to_langchain_user(self):
        """Test converting user message to LangChain format."""
        from langchain_core.messages import HumanMessage

        msg = Message(role="user", content="Hello")
        lc_msg = msg.to_langchain()
        assert isinstance(lc_msg, HumanMessage)
        assert lc_msg.content == "Hello"

    def test_to_langchain_assistant(self):
        """Test converting assistant message to LangChain format."""
        from langchain_core.messages import AIMessage

        msg = Message(role="assistant", content="Hi there")
        lc_msg = msg.to_langchain()
        assert isinstance(lc_msg, AIMessage)
        assert lc_msg.content == "Hi there"


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_create_response(self):
        """Test creating a response."""
        response = LLMResponse(
            content="Hello!",
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
        )
        assert response.content == "Hello!"
        assert response.model == "test-model"
        assert response.usage["prompt_tokens"] == 10

    def test_response_defaults(self):
        """Test response default values."""
        response = LLMResponse(content="test", model="model")
        assert response.usage == {}
        assert response.raw_response is None


class TestProviderFactory:
    """Tests for provider factory."""

    def test_unknown_provider_raises_error(self):
        """Test that unknown provider raises error."""
        with pytest.raises(LLMConfigError, match="Unknown provider"):
            get_provider(provider_name="unknown", api_key="test")  # type: ignore

    def test_missing_openai_key_raises_error(self):
        """Test that missing OpenAI key raises error."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(LLMConfigError, match="OpenAI API key"):
                get_provider(provider_name="openai")

    def test_missing_anthropic_key_raises_error(self):
        """Test that missing Anthropic key raises error."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(LLMConfigError, match="Anthropic API key"):
                get_provider(provider_name="claude")

    def test_create_openai_provider(self):
        """Test creating OpenAI provider."""
        provider = get_provider(
            provider_name="openai",
            api_key="test-key",
            model="gpt-4",
        )
        assert isinstance(provider, LLMProvider)
        assert provider.model_name == "gpt-4"

    def test_create_claude_provider(self):
        """Test creating Claude provider."""
        provider = get_provider(
            provider_name="claude",
            api_key="test-key",
            model="claude-sonnet-4-20250514",
        )
        assert isinstance(provider, LLMProvider)
        assert provider.model_name == "claude-sonnet-4-20250514"

    def test_get_model_openai(self):
        """Test getting raw OpenAI model."""
        from langchain_openai import ChatOpenAI

        model = get_model(provider_name="openai", api_key="test-key")
        assert isinstance(model, ChatOpenAI)

    def test_get_model_claude(self):
        """Test getting raw Claude model."""
        from langchain_anthropic import ChatAnthropic

        model = get_model(provider_name="claude", api_key="test-key")
        assert isinstance(model, ChatAnthropic)


class TestLLMProvider:
    """Tests for LLMProvider wrapper."""

    def test_create_chain(self):
        """Test creating a chain with system prompt."""
        mock_model = MagicMock()
        provider = LLMProvider(model=mock_model, model_name="test")

        chain = provider.create_chain("You are helpful")
        assert chain is not None

    def test_create_structured_chain(self):
        """Test creating a structured output chain."""
        mock_model = MagicMock()
        mock_model.with_structured_output.return_value = mock_model
        provider = LLMProvider(model=mock_model, model_name="test")

        chain = provider.create_structured_chain(
            "You are helpful",
            RequirementsAnalysis,
        )
        assert chain is not None
        mock_model.with_structured_output.assert_called_once_with(RequirementsAnalysis)


class TestSchemas:
    """Tests for Pydantic schemas."""

    def test_requirements_analysis(self):
        """Test RequirementsAnalysis schema."""
        req = RequirementsAnalysis(
            summary="Add feature",
            tasks=["Task 1", "Task 2"],
            files_to_modify=["file.py"],
            files_to_create=["new.py"],
            test_requirements=["Test it"],
            dependencies=[],
        )
        assert req.summary == "Add feature"
        assert len(req.tasks) == 2
        assert "file.py" in req.files_to_modify

    def test_code_review(self):
        """Test CodeReview schema."""
        review = CodeReview(
            assessment="Looks good",
            issues=[],
            requirements_met=True,
            requirements_notes="All done",
            approved=True,
        )
        assert review.approved is True
        assert review.requirements_met is True
        assert review.assessment == "Looks good"

    def test_code_review_with_issues(self):
        """Test CodeReview with issues."""
        from patcher.llm.schemas import ReviewIssue

        issue = ReviewIssue(
            severity="error",
            file_path="test.py",
            line=10,
            description="Bug found",
            suggestion="Fix it",
        )
        review = CodeReview(
            assessment="Has issues",
            issues=[issue],
            requirements_met=False,
            approved=False,
        )
        assert len(review.issues) == 1
        assert review.issues[0].severity == "error"
        assert review.approved is False
