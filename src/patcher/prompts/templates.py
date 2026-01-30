"""Prompt templates for patcher agents."""

# =============================================================================
# CODE GENERATION PROMPT
# =============================================================================

CODE_GENERATION_PROMPT = """Based on the codebase analysis, implement the changes for this issue.

Issue #{issue_number}: {issue_title}
{issue_body}

Codebase Analysis:
{repo_context}

{few_shot_examples}

Generate the complete content for each file that needs to be created or modified.
For each file, specify:
- path: the file path relative to repository root
- content: complete file content
- action: 'create' for new files, 'modify' for existing files

Follow the existing code patterns and style found in the repository.

IMPORTANT:
- Do NOT create or modify GitHub Actions workflow files
- Focus only on source code, tests, and documentation"""


# =============================================================================
# CODE FIX PROMPT (based on review feedback)
# =============================================================================

CODE_FIX_PROMPT = """Fix the code based on this review feedback.

Original Issue #{issue_number}: {issue_title}
{issue_body}

Review Feedback:
{feedback}

Analysis:
{repo_context}

{few_shot_examples}

Generate the fixed content for each file that needs changes.
Address all the feedback points in your fixes.

For each file, specify:
- path: the file path
- content: complete fixed file content
- action: 'modify' for existing files"""


# =============================================================================
# CI ANALYSIS AND FIX PROMPT
# =============================================================================

CI_ANALYSIS_PROMPT = """Analyze the CI failures and generate fixes.

Original Issue #{issue_number}: {issue_title}
{issue_body}

CI Failures:
{ci_failures}

Failed Check Details:
{ci_details}

Current File Contents:
{file_contents}

{few_shot_examples}

Analyze each CI failure and generate the necessary fixes:

1. For linting errors (ruff, flake8, eslint):
   - Identify the exact line and error
   - Fix formatting, imports, or style issues

2. For type errors (mypy, pyright, typescript):
   - Fix type annotations
   - Add missing types
   - Correct type mismatches

3. For test failures (pytest, jest):
   - Analyze the assertion error
   - Fix the implementation or update the test
   - Ensure the fix aligns with requirements

4. For build errors:
   - Fix syntax errors
   - Resolve import issues
   - Fix dependency problems

Generate the fixed content for each file that needs changes.
For each file, specify:
- path: the file path
- content: complete fixed file content
- action: 'modify' for existing files

IMPORTANT: Only fix what's needed to pass CI. Don't refactor or add features."""


# =============================================================================
# REVIEW PROMPT
# =============================================================================

REVIEW_PROMPT = """Review this pull request diff.

PR Title: {pr_title}
PR Description: {pr_body}
{issue_context}

Diff:
```diff
{diff}
```

{few_shot_examples}

Analyze the code changes and provide:
1. Overall assessment of the implementation
2. Any issues found (bugs, security, performance, style)
3. Whether the implementation meets the requirements (if issue provided)
4. Whether the PR should be approved

For each issue found, specify:
- severity: 'error', 'warning', or 'info'
- file_path: the file where the issue was found
- line: line number if applicable
- description: what the issue is
- suggestion: how to fix it

IMPORTANT: If the PR contains changes to GitHub Actions workflows or CI/CD configuration, flag this as an error."""
