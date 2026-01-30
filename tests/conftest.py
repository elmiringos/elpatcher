"""Pytest fixtures for patcher tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider for testing."""
    from patcher.llm.provider import LLMResponse

    provider = AsyncMock()
    provider.complete.return_value = LLMResponse(
        content="Generated response",
        model="test-model",
        usage={"prompt_tokens": 100, "completion_tokens": 200},
        raw_response={},
    )
    return provider


@pytest.fixture
def mock_github_client():
    """Mock GitHub client for testing."""
    client = MagicMock()
    client.get_issue.return_value = {
        "number": 42,
        "title": "Test issue",
        "body": "Test body",
        "labels": ["ai-agent"],
    }
    return client


@pytest.fixture
def sample_issue_data():
    """Sample issue data for testing."""
    return {
        "number": 42,
        "title": "Add user authentication",
        "body": "## Requirements\n- JWT tokens\n- Password hashing",
        "labels": ["ai-agent", "feature"],
    }


@pytest.fixture
def sample_pr_data():
    """Sample PR data for testing."""
    return {
        "number": 123,
        "title": "feat: add user authentication",
        "body": "Implements JWT-based authentication",
        "head": {"ref": "feature/auth"},
        "base": {"ref": "main"},
        "labels": ["ai-generated"],
    }
