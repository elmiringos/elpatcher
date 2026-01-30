"""Main code analyzer combining all code analysis capabilities."""

from pathlib import Path

from patcher.code.repo_map import RepoMapper, RepoMap
from patcher.code.search import CodeSearcher, SearchResult


class CodeAnalyzer:
    """Unified code analyzer with search, mapping, and language detection."""

    def __init__(self, repo_path: Path | str):
        """Initialize code analyzer.

        Args:
            repo_path: Path to the repository
        """
        self.repo_path = Path(repo_path)
        self.searcher = CodeSearcher(self.repo_path)
        self.mapper = RepoMapper(self.repo_path)

    def search(self, pattern: str, **kwargs) -> SearchResult:
        """Search for a pattern in the codebase.

        Args:
            pattern: Search pattern
            **kwargs: Additional search options

        Returns:
            SearchResult
        """
        return self.searcher.search(pattern, **kwargs)

    def find_definition(self, symbol: str, language: str | None = None) -> SearchResult:
        """Find where a symbol is defined.

        Args:
            symbol: Symbol name
            language: Optional language hint

        Returns:
            SearchResult with definition locations
        """
        return self.searcher.find_definition(symbol, language)

    def find_references(self, symbol: str, **kwargs) -> SearchResult:
        """Find all references to a symbol.

        Args:
            symbol: Symbol name
            **kwargs: Additional options

        Returns:
            SearchResult with references
        """
        return self.searcher.find_references(symbol, **kwargs)

    def get_repo_map(self, **kwargs) -> RepoMap:
        """Get a map of the repository structure.

        Args:
            **kwargs: Options for create_map

        Returns:
            RepoMap object
        """
        return self.mapper.create_map(**kwargs)

    def get_file_tree(self, max_depth: int = 3) -> str:
        """Get repository as a tree structure.

        Args:
            max_depth: Maximum depth

        Returns:
            Tree-formatted string
        """
        return self.mapper.format_tree(max_depth)

    def get_symbols_map(self, max_files: int = 50) -> str:
        """Get repository with code symbols.

        Args:
            max_files: Maximum files

        Returns:
            Formatted symbols map
        """
        return self.mapper.format_symbols_map(max_files)

    def detect_languages(self) -> dict[str, int]:
        """Detect languages used in the repository.

        Returns:
            Dictionary of language -> file count
        """
        return self.mapper.detect_languages()

    def read_file(self, path: str) -> str:
        """Read a file from the repository.

        Args:
            path: File path relative to repo root

        Returns:
            File content
        """
        full_path = self.repo_path / path
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if not full_path.is_file():
            raise ValueError(f"Path is not a file: {path}")

        return full_path.read_text(errors="ignore")

    def list_files(
        self,
        path: str = "",
        *,
        recursive: bool = False,
        pattern: str | None = None,
    ) -> list[str]:
        """List files in a directory.

        Args:
            path: Directory path relative to repo root
            recursive: Whether to list recursively
            pattern: Glob pattern to filter files

        Returns:
            List of file paths
        """
        base = self.repo_path / path if path else self.repo_path

        if not base.exists():
            raise FileNotFoundError(f"Directory not found: {path}")

        if recursive:
            if pattern:
                files = base.rglob(pattern)
            else:
                files = base.rglob("*")
        else:
            if pattern:
                files = base.glob(pattern)
            else:
                files = base.iterdir()

        result = []
        for f in files:
            if f.is_file():
                # Skip common non-code
                path_str = str(f)
                if any(x in path_str for x in [".git", "node_modules", "__pycache__"]):
                    continue
                result.append(str(f.relative_to(self.repo_path)))

        return sorted(result)[:500]  # Limit

    def get_context_for_issue(self, issue_text: str) -> str:
        """Get relevant context from the codebase for an issue.

        Args:
            issue_text: Issue title and body

        Returns:
            Relevant code context
        """
        import re

        context_parts = []

        # Extract potential file paths from issue
        file_patterns = re.findall(r'[\w/.-]+\.(py|js|ts|go|rs|java|c|cpp|h)', issue_text)
        for pattern in file_patterns[:5]:
            try:
                content = self.read_file(pattern)
                context_parts.append(f"--- {pattern} ---\n{content[:3000]}")
            except Exception:
                pass

        # Extract potential function/class names
        symbols = re.findall(r'\b([A-Z][a-zA-Z0-9]+|[a-z_][a-zA-Z0-9_]+)\b', issue_text)
        # Filter common words
        common_words = {"the", "and", "for", "with", "this", "that", "from", "have", "will", "should", "would", "could"}
        symbols = [s for s in symbols if s.lower() not in common_words and len(s) > 2]

        for symbol in symbols[:5]:
            result = self.find_definition(symbol)
            if result.matches:
                for match in result.matches[:2]:
                    context_parts.append(
                        f"--- {match.path}:{match.line} (definition of {symbol}) ---\n"
                        f"{match.line_content}"
                    )

        # Add repo structure
        context_parts.insert(0, f"Repository structure:\n{self.get_file_tree(max_depth=2)}")

        # Add symbols map
        context_parts.append(f"\nCode symbols:\n{self.get_symbols_map(max_files=20)}")

        return "\n\n".join(context_parts)[:15000]  # Limit total context
