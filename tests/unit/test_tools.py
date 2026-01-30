"""Unit tests for LangChain tools."""

import pytest
from unittest.mock import MagicMock

from patcher.agents.tools import (
    create_github_tools,
    create_code_analysis_tools,
    create_all_tools,
)


class TestGitHubTools:
    """Tests for GitHub tools."""

    def test_create_github_tools(self):
        """Test creating GitHub tools."""
        mock_client = MagicMock()
        tools = create_github_tools(mock_client)

        assert len(tools) == 6

        # Check tool names
        tool_names = [t.name for t in tools]
        assert "get_file_content" in tool_names
        assert "list_repository_files" in tool_names
        assert "get_issue_details" in tool_names
        assert "get_pr_details" in tool_names
        assert "get_pr_diff" in tool_names
        assert "get_ci_status" in tool_names

    def test_get_file_content_tool(self):
        """Test get_file_content tool."""
        mock_client = MagicMock()
        mock_client.get_file_content.return_value = "file content"

        tools = create_github_tools(mock_client)
        get_file = next(t for t in tools if t.name == "get_file_content")

        result = get_file.invoke({"path": "test.py", "ref": "main"})

        assert result == "file content"
        mock_client.get_file_content.assert_called_once_with("test.py", ref="main")

    def test_get_file_content_error(self):
        """Test get_file_content handles errors."""
        mock_client = MagicMock()
        mock_client.get_file_content.side_effect = Exception("Not found")

        tools = create_github_tools(mock_client)
        get_file = next(t for t in tools if t.name == "get_file_content")

        result = get_file.invoke({"path": "missing.py", "ref": "main"})

        assert "Error" in result

    def test_list_repository_files_tool(self):
        """Test list_repository_files tool."""
        mock_client = MagicMock()
        mock_client.list_files.return_value = ["file1.py", "file2.py"]

        tools = create_github_tools(mock_client)
        list_files = next(t for t in tools if t.name == "list_repository_files")

        result = list_files.invoke({"path": "src", "ref": "main"})

        assert "file1.py" in result
        assert "file2.py" in result

    def test_get_issue_details_tool(self):
        """Test get_issue_details tool."""
        mock_client = MagicMock()
        mock_issue = MagicMock()
        mock_issue.number = 42
        mock_issue.title = "Test Issue"
        mock_issue.state = "open"
        mock_issue.labels = ["bug"]
        mock_issue.body = "Issue body"
        mock_client.get_issue.return_value = mock_issue

        tools = create_github_tools(mock_client)
        get_issue = next(t for t in tools if t.name == "get_issue_details")

        result = get_issue.invoke({"issue_number": 42})

        assert "Issue #42" in result
        assert "Test Issue" in result
        assert "Issue body" in result


class TestCodeAnalysisTools:
    """Tests for code analysis tools."""

    def test_create_code_analysis_tools(self):
        """Test creating code analysis tools."""
        tools = create_code_analysis_tools()

        assert len(tools) == 3

        tool_names = [t.name for t in tools]
        assert "analyze_python_code" in tool_names
        assert "check_code_style" in tool_names
        assert "extract_functions" in tool_names

    def test_analyze_python_code_finds_issues(self):
        """Test analyze_python_code finds common issues."""
        tools = create_code_analysis_tools()
        analyze = next(t for t in tools if t.name == "analyze_python_code")

        code_with_issues = """
from module import *
password = "secret123"
eval("dangerous")
# TODO: fix this
"""
        result = analyze.invoke({"code": code_with_issues})

        assert "import *" in result
        assert "password" in result.lower() or "Password" in result
        assert "eval" in result.lower()
        assert "TODO" in result

    def test_analyze_python_code_clean(self):
        """Test analyze_python_code with clean code."""
        tools = create_code_analysis_tools()
        analyze = next(t for t in tools if t.name == "analyze_python_code")

        clean_code = """
def greet(name: str) -> str:
    return f"Hello, {name}!"
"""
        result = analyze.invoke({"code": clean_code})

        assert "No obvious issues" in result

    def test_extract_functions(self):
        """Test extract_functions tool."""
        tools = create_code_analysis_tools()
        extract = next(t for t in tools if t.name == "extract_functions")

        code = """
class MyClass:
    def method(self):
        pass

def standalone_function(arg1, arg2):
    pass
"""
        result = extract.invoke({"code": code})

        assert "class MyClass" in result
        assert "def method" in result
        assert "def standalone_function" in result


class TestAllTools:
    """Tests for create_all_tools."""

    def test_create_all_tools_with_github(self):
        """Test creating all tools with GitHub client."""
        mock_client = MagicMock()
        tools = create_all_tools(github_client=mock_client)

        # Should have GitHub tools + code analysis tools
        assert len(tools) == 9  # 6 GitHub + 3 code analysis

    def test_create_all_tools_without_github(self):
        """Test creating all tools without GitHub client."""
        tools = create_all_tools(github_client=None)

        # Should only have code analysis tools
        assert len(tools) == 3
