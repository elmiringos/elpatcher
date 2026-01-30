"""Few-shot examples for patcher agents.

Fill in these examples to improve agent performance.
Each example should demonstrate the expected input/output format.
"""

# =============================================================================
# CODE GENERATION EXAMPLES
# =============================================================================
# Examples of generating code from issue descriptions
# Format: list of {"issue": str, "context": str, "response": str}

CODE_GENERATION_EXAMPLES: list[dict] = [
    # Example 1: Add a new function
    # {
    #     "issue": """
    #     Issue #42: Add greeting function
    #     Create a function that returns a greeting message with the user's name.
    #     """,
    #     "context": """
    #     Repository structure:
    #     - src/utils.py (utility functions)
    #     - src/main.py (entry point)
    #     - tests/test_utils.py (tests)
    #     """,
    #     "response": """
    #     {
    #         "files": [
    #             {
    #                 "path": "src/utils.py",
    #                 "content": "def greet(name: str) -> str:\\n    return f\\"Hello, {name}!\\"",
    #                 "action": "modify"
    #             },
    #             {
    #                 "path": "tests/test_utils.py",
    #                 "content": "def test_greet():\\n    assert greet(\\"World\\") == \\"Hello, World!\\"",
    #                 "action": "modify"
    #             }
    #         ],
    #         "explanation": "Added greet function with test"
    #     }
    #     """
    # },

    # Example 2: Fix a bug
    # {
    #     "issue": "...",
    #     "context": "...",
    #     "response": "..."
    # },
]


# =============================================================================
# CODE FIX EXAMPLES (based on review feedback)
# =============================================================================
# Examples of fixing code based on review comments
# Format: list of {"feedback": str, "original_code": str, "fixed_code": str}

CODE_FIX_EXAMPLES: list[dict] = [
    # Example 1: Fix missing error handling
    # {
    #     "feedback": """
    #     [ERROR] src/api.py:25 - Missing null check for user input
    #     Suggestion: Add validation before processing
    #     """,
    #     "original_code": """
    #     def process_user(name):
    #         return name.upper()
    #     """,
    #     "fixed_code": """
    #     def process_user(name: str | None) -> str:
    #         if not name:
    #             raise ValueError("Name cannot be empty")
    #         return name.upper()
    #     """
    # },

    # Example 2: Fix type hints
    # {
    #     "feedback": "...",
    #     "original_code": "...",
    #     "fixed_code": "..."
    # },
]


# =============================================================================
# CI FIX EXAMPLES
# =============================================================================
# Examples of fixing code based on CI failures
# Format: list of {"ci_error": str, "file_content": str, "fix": str}

CI_FIX_EXAMPLES: list[dict] = [
    # Example 1: Fix linting error
    # {
    #     "ci_error": """
    #     ruff check failed:
    #     src/main.py:10:1: E302 expected 2 blank lines, found 1
    #     """,
    #     "file_content": """
    #     import os
    #     def main():
    #         pass
    #     """,
    #     "fix": """
    #     import os
    #
    #
    #     def main():
    #         pass
    #     """
    # },

    # Example 2: Fix test failure
    # {
    #     "ci_error": """
    #     pytest failed:
    #     FAILED tests/test_calc.py::test_add - AssertionError: assert 3 == 4
    #     """,
    #     "file_content": "...",
    #     "fix": "..."
    # },

    # Example 3: Fix type error
    # {
    #     "ci_error": """
    #     mypy error:
    #     src/utils.py:15: error: Incompatible return value type (got "str", expected "int")
    #     """,
    #     "file_content": "...",
    #     "fix": "..."
    # },
]


# =============================================================================
# REVIEW EXAMPLES
# =============================================================================
# Examples of code review assessments
# Format: list of {"diff": str, "issue_requirements": str, "review": str}

REVIEW_EXAMPLES: list[dict] = [
    # Example 1: Approved review
    # {
    #     "diff": """
    #     +def validate_email(email: str) -> bool:
    #     +    import re
    #     +    pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    #     +    return bool(re.match(pattern, email))
    #     """,
    #     "issue_requirements": "Add email validation function",
    #     "review": """
    #     {
    #         "assessment": "Clean implementation with proper regex pattern",
    #         "issues": [],
    #         "requirements_met": true,
    #         "requirements_notes": "Email validation implemented correctly",
    #         "approved": true
    #     }
    #     """
    # },

    # Example 2: Changes requested
    # {
    #     "diff": "...",
    #     "issue_requirements": "...",
    #     "review": """
    #     {
    #         "assessment": "Implementation has security issues",
    #         "issues": [
    #             {
    #                 "severity": "error",
    #                 "file_path": "src/auth.py",
    #                 "line": 42,
    #                 "description": "Password stored in plain text",
    #                 "suggestion": "Use bcrypt or argon2 for password hashing"
    #             }
    #         ],
    #         "requirements_met": false,
    #         "requirements_notes": "Security requirements not met",
    #         "approved": false
    #     }
    #     """
    # },
]


def format_few_shot_examples(examples: list[dict], template: str) -> str:
    """Format few-shot examples into a prompt string.

    Args:
        examples: List of example dictionaries
        template: Template string with placeholders matching dict keys

    Returns:
        Formatted examples string
    """
    if not examples:
        return ""

    formatted = ["Here are some examples:\n"]
    for i, example in enumerate(examples, 1):
        formatted.append(f"--- Example {i} ---")
        try:
            formatted.append(template.format(**example))
        except KeyError:
            continue
        formatted.append("")

    return "\n".join(formatted)
