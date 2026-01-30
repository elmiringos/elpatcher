"""Repository mapping with file structure and code definitions."""

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CodeSymbol:
    """A code symbol (function, class, method, etc.)."""

    name: str
    kind: str  # function, class, method, variable, interface, etc.
    line: int
    end_line: int | None = None
    signature: str | None = None
    docstring: str | None = None
    children: list["CodeSymbol"] = field(default_factory=list)


@dataclass
class FileInfo:
    """Information about a file in the repository."""

    path: str
    language: str
    size: int
    symbols: list[CodeSymbol] = field(default_factory=list)


@dataclass
class RepoMap:
    """Map of the repository structure."""

    root: str
    files: list[FileInfo]
    languages: dict[str, int]  # language -> file count
    total_files: int
    total_lines: int


# Language detection by file extension
LANGUAGE_EXTENSIONS = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".scala": "scala",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".md": "markdown",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    ".vue": "vue",
    ".svelte": "svelte",
}

# Patterns for extracting symbols from different languages
SYMBOL_PATTERNS = {
    "python": [
        (r"^(\s*)class\s+(\w+)(?:\((.*?)\))?:", "class"),
        (r"^(\s*)(?:async\s+)?def\s+(\w+)\s*\((.*?)\).*:", "function"),
        (r"^(\w+)\s*:\s*\w+\s*=", "variable"),
        (r"^(\w+)\s*=\s*", "variable"),
    ],
    "javascript": [
        (r"^(\s*)class\s+(\w+)(?:\s+extends\s+\w+)?", "class"),
        (r"^(\s*)(?:async\s+)?function\s+(\w+)\s*\(", "function"),
        (r"^(\s*)(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(.*?\)\s*=>", "function"),
        (r"^(\s*)(?:const|let|var)\s+(\w+)\s*=\s*function", "function"),
        (r"^(\s*)(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=", "variable"),
    ],
    "typescript": [
        (r"^(\s*)(?:export\s+)?class\s+(\w+)", "class"),
        (r"^(\s*)(?:export\s+)?interface\s+(\w+)", "interface"),
        (r"^(\s*)(?:export\s+)?type\s+(\w+)\s*=", "type"),
        (r"^(\s*)(?:export\s+)?(?:async\s+)?function\s+(\w+)", "function"),
        (r"^(\s*)(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(.*?\)\s*=>", "function"),
    ],
    "go": [
        (r"^type\s+(\w+)\s+struct\s*\{", "struct"),
        (r"^type\s+(\w+)\s+interface\s*\{", "interface"),
        (r"^func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(", "function"),
    ],
    "rust": [
        (r"^(\s*)(?:pub\s+)?struct\s+(\w+)", "struct"),
        (r"^(\s*)(?:pub\s+)?enum\s+(\w+)", "enum"),
        (r"^(\s*)(?:pub\s+)?trait\s+(\w+)", "trait"),
        (r"^(\s*)impl(?:<[^>]+>)?\s+(?:(\w+)\s+for\s+)?(\w+)", "impl"),
        (r"^(\s*)(?:pub\s+)?(?:async\s+)?fn\s+(\w+)", "function"),
    ],
    "java": [
        (r"^(\s*)(?:public|private|protected)?\s*(?:static)?\s*class\s+(\w+)", "class"),
        (r"^(\s*)(?:public|private|protected)?\s*interface\s+(\w+)", "interface"),
        (r"^(\s*)(?:public|private|protected)?\s*(?:static)?\s*\w+(?:<[^>]+>)?\s+(\w+)\s*\(", "method"),
    ],
}


class RepoMapper:
    """Create a map of repository structure and code symbols."""

    def __init__(self, repo_path: Path):
        """Initialize repo mapper.

        Args:
            repo_path: Path to the repository
        """
        self.repo_path = Path(repo_path)
        self._tree_sitter_available = self._check_tree_sitter()

    def _check_tree_sitter(self) -> bool:
        """Check if tree-sitter is available."""
        try:
            import tree_sitter_languages
            return True
        except ImportError:
            return False

    def detect_language(self, path: Path) -> str:
        """Detect programming language from file extension.

        Args:
            path: File path

        Returns:
            Language name or "unknown"
        """
        suffix = path.suffix.lower()
        return LANGUAGE_EXTENSIONS.get(suffix, "unknown")

    def detect_languages(self) -> dict[str, int]:
        """Detect all languages used in the repository.

        Returns:
            Dictionary of language -> file count
        """
        languages: dict[str, int] = {}

        for path in self.repo_path.rglob("*"):
            if not path.is_file():
                continue

            # Skip non-code directories
            path_str = str(path)
            if any(x in path_str for x in [".git", "node_modules", "__pycache__", ".venv", "venv"]):
                continue

            lang = self.detect_language(path)
            if lang != "unknown":
                languages[lang] = languages.get(lang, 0) + 1

        return dict(sorted(languages.items(), key=lambda x: -x[1]))

    def get_file_symbols(self, path: Path) -> list[CodeSymbol]:
        """Extract code symbols from a file.

        Args:
            path: File path

        Returns:
            List of CodeSymbol objects
        """
        language = self.detect_language(path)

        if self._tree_sitter_available:
            return self._get_symbols_tree_sitter(path, language)
        else:
            return self._get_symbols_regex(path, language)

    def _get_symbols_tree_sitter(self, path: Path, language: str) -> list[CodeSymbol]:
        """Extract symbols using tree-sitter for accurate parsing.

        Args:
            path: File path
            language: Programming language

        Returns:
            List of CodeSymbol objects
        """
        try:
            import tree_sitter_languages
        except ImportError:
            return self._get_symbols_regex(path, language)

        # Map our language names to tree-sitter names
        ts_languages = {
            "python": "python",
            "javascript": "javascript",
            "typescript": "typescript",
            "go": "go",
            "rust": "rust",
            "java": "java",
            "c": "c",
            "cpp": "cpp",
        }

        if language not in ts_languages:
            return self._get_symbols_regex(path, language)

        try:
            parser = tree_sitter_languages.get_parser(ts_languages[language])
            content = path.read_bytes()
            tree = parser.parse(content)
        except Exception:
            return self._get_symbols_regex(path, language)

        symbols = []
        content_str = content.decode("utf-8", errors="ignore")

        # Query for different node types based on language
        self._extract_tree_sitter_symbols(tree.root_node, content_str, symbols, language)

        return symbols

    def _extract_tree_sitter_symbols(
        self,
        node,
        content: str,
        symbols: list[CodeSymbol],
        language: str,
        parent_indent: int = 0,
    ) -> None:
        """Recursively extract symbols from tree-sitter AST.

        Args:
            node: Tree-sitter node
            content: File content
            symbols: List to append symbols to
            language: Programming language
            parent_indent: Parent indentation level
        """
        # Node types that represent definitions
        definition_types = {
            "python": ["function_definition", "class_definition", "assignment"],
            "javascript": ["function_declaration", "class_declaration", "variable_declaration", "arrow_function"],
            "typescript": ["function_declaration", "class_declaration", "interface_declaration", "type_alias_declaration"],
            "go": ["function_declaration", "method_declaration", "type_declaration"],
            "rust": ["function_item", "struct_item", "enum_item", "impl_item", "trait_item"],
            "java": ["class_declaration", "interface_declaration", "method_declaration"],
        }

        lang_types = definition_types.get(language, [])

        if node.type in lang_types:
            name_node = None
            for child in node.children:
                if child.type in ["identifier", "name", "type_identifier"]:
                    name_node = child
                    break

            if name_node:
                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1
                name = content[name_node.start_byte:name_node.end_byte]

                kind = node.type.replace("_definition", "").replace("_declaration", "").replace("_item", "")

                symbols.append(CodeSymbol(
                    name=name,
                    kind=kind,
                    line=start_line,
                    end_line=end_line,
                    signature=None,  # Could extract from node
                ))

        # Recurse into children
        for child in node.children:
            self._extract_tree_sitter_symbols(child, content, symbols, language, parent_indent)

    def _get_symbols_regex(self, path: Path, language: str) -> list[CodeSymbol]:
        """Extract symbols using regex patterns (fallback).

        Args:
            path: File path
            language: Programming language

        Returns:
            List of CodeSymbol objects
        """
        patterns = SYMBOL_PATTERNS.get(language, [])
        if not patterns:
            return []

        try:
            content = path.read_text(errors="ignore")
        except Exception:
            return []

        symbols = []
        lines = content.split("\n")

        for i, line in enumerate(lines, 1):
            for pattern, kind in patterns:
                match = re.match(pattern, line)
                if match:
                    groups = match.groups()
                    # Find the name (usually second group after indent)
                    name = None
                    for g in groups:
                        if g and not g.isspace() and g not in ("async", "export", "public", "private", "static"):
                            name = g
                            break

                    if name and not name.startswith("_"):  # Skip private
                        symbols.append(CodeSymbol(
                            name=name,
                            kind=kind,
                            line=i,
                            signature=line.strip()[:100],
                        ))
                    break

        return symbols

    def create_map(
        self,
        *,
        include_symbols: bool = True,
        max_files: int = 500,
        extensions: list[str] | None = None,
    ) -> RepoMap:
        """Create a complete map of the repository.

        Args:
            include_symbols: Whether to extract code symbols
            max_files: Maximum number of files to process
            extensions: Only include files with these extensions

        Returns:
            RepoMap object
        """
        files: list[FileInfo] = []
        languages: dict[str, int] = {}
        total_lines = 0

        for path in self.repo_path.rglob("*"):
            if not path.is_file():
                continue

            # Skip non-code directories
            path_str = str(path)
            if any(x in path_str for x in [".git", "node_modules", "__pycache__", ".venv", "venv", ".tox"]):
                continue

            # Filter by extension
            if extensions and path.suffix.lower() not in extensions:
                continue

            language = self.detect_language(path)
            if language == "unknown":
                continue

            languages[language] = languages.get(language, 0) + 1

            try:
                size = path.stat().st_size
                line_count = sum(1 for _ in open(path, errors="ignore"))
                total_lines += line_count
            except Exception:
                size = 0
                line_count = 0

            symbols = []
            if include_symbols and size < 500_000:  # Skip large files
                symbols = self.get_file_symbols(path)

            rel_path = str(path.relative_to(self.repo_path))
            files.append(FileInfo(
                path=rel_path,
                language=language,
                size=size,
                symbols=symbols,
            ))

            if len(files) >= max_files:
                break

        return RepoMap(
            root=str(self.repo_path),
            files=sorted(files, key=lambda f: f.path),
            languages=dict(sorted(languages.items(), key=lambda x: -x[1])),
            total_files=len(files),
            total_lines=total_lines,
        )

    def format_tree(self, max_depth: int = 3) -> str:
        """Format repository as a tree structure.

        Args:
            max_depth: Maximum directory depth to show

        Returns:
            Tree-formatted string
        """
        lines = []
        seen_dirs: set[str] = set()

        for path in sorted(self.repo_path.rglob("*")):
            rel_path = path.relative_to(self.repo_path)
            parts = rel_path.parts

            # Skip hidden and common non-code
            if any(p.startswith(".") or p in ["node_modules", "__pycache__", "venv", ".venv"] for p in parts):
                continue

            if len(parts) > max_depth:
                continue

            depth = len(parts) - 1
            indent = "  " * depth

            if path.is_dir():
                dir_path = str(rel_path)
                if dir_path not in seen_dirs:
                    lines.append(f"{indent}{path.name}/")
                    seen_dirs.add(dir_path)
            else:
                lines.append(f"{indent}{path.name}")

        return "\n".join(lines[:200])  # Limit output

    def format_symbols_map(self, max_files: int = 50) -> str:
        """Format repository with file symbols.

        Args:
            max_files: Maximum files to include

        Returns:
            Formatted string with file paths and their symbols
        """
        repo_map = self.create_map(include_symbols=True, max_files=max_files)
        lines = []

        for file_info in repo_map.files:
            if not file_info.symbols:
                continue

            lines.append(f"\n{file_info.path}:")

            for symbol in file_info.symbols:
                indent = "  "
                if symbol.kind in ("method", "function") and symbol.line > 1:
                    indent = "    "
                lines.append(f"{indent}{symbol.kind} {symbol.name} (line {symbol.line})")

        if not lines:
            return "No code symbols found in repository."

        # Add summary
        summary = f"Languages: {', '.join(f'{k}({v})' for k, v in list(repo_map.languages.items())[:5])}"
        return f"{summary}\n{'=' * 40}" + "\n".join(lines)
