"""Code search using ripgrep."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SearchMatch:
    """A single search match."""

    path: str
    line_number: int
    line_content: str
    context_before: list[str]
    context_after: list[str]


@dataclass
class SearchResult:
    """Result of a code search."""

    query: str
    matches: list[SearchMatch]
    total_matches: int
    truncated: bool = False


class CodeSearcher:
    """Code search using ripgrep for fast pattern matching."""

    def __init__(self, repo_path: Path):
        """Initialize code searcher.

        Args:
            repo_path: Path to the repository
        """
        self.repo_path = Path(repo_path)

    def search(
        self,
        pattern: str,
        *,
        file_pattern: str | None = None,
        context_lines: int = 2,
        max_results: int = 50,
        case_sensitive: bool = False,
        regex: bool = True,
    ) -> SearchResult:
        """Search for a pattern in the codebase.

        Args:
            pattern: Search pattern (regex by default)
            file_pattern: Glob pattern to filter files (e.g., "*.py")
            context_lines: Number of context lines before/after match
            max_results: Maximum number of results to return
            case_sensitive: Whether search is case sensitive
            regex: Whether to treat pattern as regex

        Returns:
            SearchResult with matches
        """
        cmd = ["rg", "--json"]

        if not case_sensitive:
            cmd.append("-i")

        if not regex:
            cmd.append("-F")

        if context_lines > 0:
            cmd.extend(["-C", str(context_lines)])

        if file_pattern:
            cmd.extend(["-g", file_pattern])

        # Exclude common non-code directories
        cmd.extend([
            "--hidden",
            "-g", "!.git",
            "-g", "!node_modules",
            "-g", "!__pycache__",
            "-g", "!*.pyc",
            "-g", "!.venv",
            "-g", "!venv",
            "-g", "!dist",
            "-g", "!build",
        ])

        cmd.extend([pattern, str(self.repo_path)])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError:
            # ripgrep not installed, fall back to grep
            return self._fallback_search(pattern, file_pattern, max_results)
        except subprocess.TimeoutExpired:
            return SearchResult(
                query=pattern,
                matches=[],
                total_matches=0,
                truncated=True,
            )

        matches = self._parse_rg_output(result.stdout)
        truncated = len(matches) > max_results

        return SearchResult(
            query=pattern,
            matches=matches[:max_results],
            total_matches=len(matches),
            truncated=truncated,
        )

    def _parse_rg_output(self, output: str) -> list[SearchMatch]:
        """Parse ripgrep JSON output.

        Args:
            output: JSON lines output from ripgrep

        Returns:
            List of SearchMatch objects
        """
        matches = []
        current_match = None
        context_before = []
        context_after = []

        for line in output.strip().split("\n"):
            if not line:
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type")

            if msg_type == "match":
                # Save previous match if exists
                if current_match:
                    current_match.context_before = context_before.copy()
                    current_match.context_after = context_after.copy()
                    matches.append(current_match)

                match_data = data.get("data", {})
                path = match_data.get("path", {}).get("text", "")
                line_number = match_data.get("line_number", 0)
                lines = match_data.get("lines", {}).get("text", "").rstrip()

                # Make path relative to repo
                if path.startswith(str(self.repo_path)):
                    path = path[len(str(self.repo_path)):].lstrip("/")

                current_match = SearchMatch(
                    path=path,
                    line_number=line_number,
                    line_content=lines,
                    context_before=[],
                    context_after=[],
                )
                context_before = []
                context_after = []

            elif msg_type == "context":
                ctx_data = data.get("data", {})
                ctx_line = ctx_data.get("lines", {}).get("text", "").rstrip()
                ctx_line_num = ctx_data.get("line_number", 0)

                if current_match:
                    if ctx_line_num < current_match.line_number:
                        context_before.append(ctx_line)
                    else:
                        context_after.append(ctx_line)

        # Don't forget the last match
        if current_match:
            current_match.context_before = context_before.copy()
            current_match.context_after = context_after.copy()
            matches.append(current_match)

        return matches

    def _fallback_search(
        self,
        pattern: str,
        file_pattern: str | None,
        max_results: int,
    ) -> SearchResult:
        """Fallback search using Python when ripgrep is not available.

        Args:
            pattern: Search pattern
            file_pattern: File glob pattern
            max_results: Maximum results

        Returns:
            SearchResult
        """
        import fnmatch
        import re

        matches = []
        pattern_re = re.compile(pattern, re.IGNORECASE)

        for path in self.repo_path.rglob("*"):
            if not path.is_file():
                continue

            # Skip common non-code paths
            path_str = str(path)
            if any(x in path_str for x in [".git", "node_modules", "__pycache__", ".venv"]):
                continue

            # Apply file pattern filter
            if file_pattern and not fnmatch.fnmatch(path.name, file_pattern):
                continue

            try:
                content = path.read_text(errors="ignore")
            except Exception:
                continue

            for i, line in enumerate(content.split("\n"), 1):
                if pattern_re.search(line):
                    rel_path = str(path.relative_to(self.repo_path))
                    matches.append(SearchMatch(
                        path=rel_path,
                        line_number=i,
                        line_content=line.rstrip(),
                        context_before=[],
                        context_after=[],
                    ))

                    if len(matches) >= max_results:
                        return SearchResult(
                            query=pattern,
                            matches=matches,
                            total_matches=len(matches),
                            truncated=True,
                        )

        return SearchResult(
            query=pattern,
            matches=matches,
            total_matches=len(matches),
            truncated=False,
        )

    def find_definition(
        self,
        symbol: str,
        language: str | None = None,
    ) -> SearchResult:
        """Find definition of a symbol (function, class, variable).

        Args:
            symbol: Symbol name to find
            language: Programming language (for better patterns)

        Returns:
            SearchResult with definition locations
        """
        # Language-specific definition patterns
        patterns = {
            "python": rf"^\s*(def|class|async def)\s+{symbol}\s*[(\[]",
            "javascript": rf"^\s*(function|class|const|let|var)\s+{symbol}\s*[=(]",
            "typescript": rf"^\s*(function|class|const|let|interface|type)\s+{symbol}\s*[=(<]",
            "go": rf"^\s*(func|type)\s+(\([^)]+\)\s+)?{symbol}\s*[(\[]",
            "rust": rf"^\s*(fn|struct|enum|trait|impl)\s+{symbol}\s*[<({{]",
            "java": rf"^\s*(public|private|protected)?\s*(static)?\s*\w+\s+{symbol}\s*\(",
        }

        file_patterns = {
            "python": "*.py",
            "javascript": "*.js",
            "typescript": "*.ts",
            "go": "*.go",
            "rust": "*.rs",
            "java": "*.java",
        }

        if language and language in patterns:
            return self.search(
                patterns[language],
                file_pattern=file_patterns.get(language),
                context_lines=3,
            )

        # Try all patterns
        all_matches = []
        for lang, pattern in patterns.items():
            result = self.search(
                pattern,
                file_pattern=file_patterns.get(lang),
                context_lines=3,
                max_results=10,
            )
            all_matches.extend(result.matches)

        return SearchResult(
            query=f"definition:{symbol}",
            matches=all_matches[:20],
            total_matches=len(all_matches),
            truncated=len(all_matches) > 20,
        )

    def find_references(
        self,
        symbol: str,
        *,
        file_pattern: str | None = None,
    ) -> SearchResult:
        """Find all references to a symbol.

        Args:
            symbol: Symbol name to find references for
            file_pattern: Optional file pattern to filter

        Returns:
            SearchResult with all references
        """
        # Match word boundaries
        return self.search(
            rf"\b{symbol}\b",
            file_pattern=file_pattern,
            context_lines=1,
            max_results=100,
        )
