"""LangChain tools for patcher agents."""

from pathlib import Path
from typing import Annotated

from langchain_core.tools import tool
from pydantic import Field


def create_github_tools(github_client):
    """Create GitHub-related tools for agents.

    Args:
        github_client: GitHubClient instance

    Returns:
        List of LangChain tools
    """

    @tool
    def get_file_content(
        path: Annotated[str, Field(description="File path in the repository")],
        ref: Annotated[str | None, Field(description="Branch or commit ref. Leave empty for default branch.")] = None,
    ) -> str:
        """Get the content of a file from the repository."""
        try:
            return github_client.get_file_content(path, ref=ref)
        except Exception as e:
            return f"Error reading file: {e}"

    @tool
    def list_repository_files(
        path: Annotated[str, Field(description="Directory path to list")] = "",
        ref: Annotated[str | None, Field(description="Branch or commit ref. Leave empty for default branch.")] = None,
    ) -> str:
        """List files in a repository directory."""
        try:
            files = github_client.list_files(path, ref=ref)
            return "\n".join(files[:100])  # Limit to 100 files
        except Exception as e:
            return f"Error listing files: {e}"

    @tool
    def get_issue_details(
        issue_number: Annotated[int, Field(description="Issue number")],
    ) -> str:
        """Get details of a GitHub issue."""
        try:
            issue = github_client.get_issue(issue_number)
            return f"""Issue #{issue.number}: {issue.title}
State: {issue.state}
Labels: {', '.join(issue.labels)}

{issue.body}"""
        except Exception as e:
            return f"Error getting issue: {e}"

    @tool
    def get_pr_details(
        pr_number: Annotated[int, Field(description="Pull request number")],
    ) -> str:
        """Get details of a GitHub pull request."""
        try:
            pr = github_client.get_pr(pr_number)
            return f"""PR #{pr.number}: {pr.title}
State: {pr.state}
Branch: {pr.head_branch} -> {pr.base_branch}
Labels: {', '.join(pr.labels)}
Mergeable: {pr.mergeable}

{pr.body}"""
        except Exception as e:
            return f"Error getting PR: {e}"

    @tool
    def get_pr_diff(
        pr_number: Annotated[int, Field(description="Pull request number")],
    ) -> str:
        """Get the diff of a pull request."""
        try:
            diff = github_client.get_pr_diff(pr_number)
            return diff[:10000]  # Limit size
        except Exception as e:
            return f"Error getting diff: {e}"

    @tool
    def get_ci_status(
        pr_number: Annotated[int, Field(description="Pull request number")],
    ) -> str:
        """Get CI status for a pull request."""
        try:
            result = github_client.get_ci_status(pr_number)
            status_lines = [f"Overall: {result.status.value}"]
            for check in result.checks:
                status_lines.append(f"  - {check.name}: {check.status.value}")
            return "\n".join(status_lines)
        except Exception as e:
            return f"Error getting CI status: {e}"

    return [
        get_file_content,
        list_repository_files,
        get_issue_details,
        get_pr_details,
        get_pr_diff,
        get_ci_status,
    ]


def create_code_analysis_tools(repo_path: Path | str | None = None):
    """Create code analysis tools for agents.

    Args:
        repo_path: Path to local repository clone

    Returns:
        List of LangChain tools
    """
    from patcher.code.analyzer import CodeAnalyzer

    # Will be initialized when repo is cloned
    _analyzer: CodeAnalyzer | None = None

    def get_analyzer() -> CodeAnalyzer:
        nonlocal _analyzer
        if _analyzer is None:
            if repo_path is None:
                raise ValueError("Repository path not set. Clone the repository first.")
            _analyzer = CodeAnalyzer(repo_path)
        return _analyzer

    @tool
    def read_file(
        path: Annotated[str, Field(description="File path relative to repository root")],
    ) -> str:
        """Read the content of a file from the local repository.

        Use this to read source code files to understand their implementation.
        """
        try:
            analyzer = get_analyzer()
            content = analyzer.read_file(path)
            lines = content.split("\n")
            # Add line numbers
            numbered = [f"{i:4d} | {line}" for i, line in enumerate(lines, 1)]
            return "\n".join(numbered[:500])  # Limit to 500 lines
        except Exception as e:
            return f"Error reading file: {e}"

    @tool
    def search_code(
        pattern: Annotated[str, Field(description="Search pattern (regex supported)")],
        file_pattern: Annotated[str | None, Field(description="Glob pattern to filter files, e.g., '*.py'")] = None,
    ) -> str:
        """Search for a pattern in the codebase using ripgrep.

        Use this to find usages of functions, classes, variables, or any code pattern.
        Returns matching lines with file paths and line numbers.
        """
        try:
            analyzer = get_analyzer()
            result = analyzer.search(
                pattern,
                file_pattern=file_pattern,
                context_lines=2,
                max_results=30,
            )

            if not result.matches:
                return f"No matches found for pattern: {pattern}"

            lines = [f"Found {result.total_matches} matches for '{pattern}'"]
            if result.truncated:
                lines.append(f"(showing first {len(result.matches)})")
            lines.append("")

            for match in result.matches:
                lines.append(f"{match.path}:{match.line_number}")
                for ctx in match.context_before:
                    lines.append(f"  | {ctx}")
                lines.append(f"  > {match.line_content}")
                for ctx in match.context_after:
                    lines.append(f"  | {ctx}")
                lines.append("")

            return "\n".join(lines)
        except Exception as e:
            return f"Error searching code: {e}"

    @tool
    def find_definition(
        symbol: Annotated[str, Field(description="Symbol name (function, class, etc.) to find")],
        language: Annotated[str | None, Field(description="Programming language hint")] = None,
    ) -> str:
        """Find where a symbol (function, class, variable) is defined.

        Use this to locate the definition of a function, class, or other symbol.
        """
        try:
            analyzer = get_analyzer()
            result = analyzer.find_definition(symbol, language)

            if not result.matches:
                return f"No definition found for symbol: {symbol}"

            lines = [f"Found {len(result.matches)} definition(s) for '{symbol}'"]
            lines.append("")

            for match in result.matches:
                lines.append(f"{match.path}:{match.line_number}")
                lines.append(f"  {match.line_content}")
                lines.append("")

            return "\n".join(lines)
        except Exception as e:
            return f"Error finding definition: {e}"

    @tool
    def find_references(
        symbol: Annotated[str, Field(description="Symbol name to find references for")],
    ) -> str:
        """Find all references to a symbol in the codebase.

        Use this to see where a function, class, or variable is used.
        """
        try:
            analyzer = get_analyzer()
            result = analyzer.find_references(symbol)

            if not result.matches:
                return f"No references found for symbol: {symbol}"

            lines = [f"Found {result.total_matches} reference(s) to '{symbol}'"]
            if result.truncated:
                lines.append(f"(showing first {len(result.matches)})")
            lines.append("")

            for match in result.matches:
                lines.append(f"{match.path}:{match.line_number}: {match.line_content.strip()}")

            return "\n".join(lines)
        except Exception as e:
            return f"Error finding references: {e}"

    @tool
    def get_repository_map() -> str:
        """Get a map of the repository showing file structure and code symbols.

        Use this at the start to understand the codebase structure, or when you need
        to find which files contain relevant code.

        Returns file tree with function and class definitions.
        """
        try:
            analyzer = get_analyzer()
            return analyzer.get_symbols_map(max_files=50)
        except Exception as e:
            return f"Error getting repository map: {e}"

    @tool
    def list_files(
        path: Annotated[str, Field(description="Directory path relative to repo root")] = "",
        recursive: Annotated[bool, Field(description="Whether to list recursively")] = False,
        pattern: Annotated[str | None, Field(description="Glob pattern, e.g., '*.py'")] = None,
    ) -> str:
        """List files in a directory of the repository.

        Use this to explore the file structure or find files matching a pattern.
        """
        try:
            analyzer = get_analyzer()
            files = analyzer.list_files(path, recursive=recursive, pattern=pattern)

            if not files:
                return f"No files found in: {path or '(root)'}"

            result = [f"Files in {path or '(root)'}:"]
            result.extend(files[:100])
            if len(files) > 100:
                result.append(f"... and {len(files) - 100} more files")

            return "\n".join(result)
        except Exception as e:
            return f"Error listing files: {e}"

    @tool
    def detect_languages() -> str:
        """Detect programming languages used in the repository.

        Returns a summary of languages by file count.
        """
        try:
            analyzer = get_analyzer()
            languages = analyzer.detect_languages()

            if not languages:
                return "No recognized programming languages found."

            lines = ["Languages in repository:"]
            for lang, count in languages.items():
                lines.append(f"  {lang}: {count} files")

            return "\n".join(lines)
        except Exception as e:
            return f"Error detecting languages: {e}"

    @tool
    def get_file_tree(
        max_depth: Annotated[int, Field(description="Maximum directory depth")] = 3,
    ) -> str:
        """Get the repository file tree structure.

        Use this for a quick overview of the project structure.
        """
        try:
            analyzer = get_analyzer()
            return analyzer.get_file_tree(max_depth)
        except Exception as e:
            return f"Error getting file tree: {e}"

    return [
        read_file,
        search_code,
        find_definition,
        find_references,
        get_repository_map,
        list_files,
        detect_languages,
        get_file_tree,
    ]


def create_all_tools(
    github_client=None,
    repo_path: Path | str | None = None,
):
    """Create all available tools.

    Args:
        github_client: Optional GitHubClient instance
        repo_path: Path to local repository clone

    Returns:
        List of all tools
    """
    tools = []

    if github_client:
        tools.extend(create_github_tools(github_client))

    if repo_path:
        tools.extend(create_code_analysis_tools(repo_path))

    return tools
