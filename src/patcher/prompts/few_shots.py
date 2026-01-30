"""Few-shot examples for patcher agents.

These examples demonstrate the expected input/output format and help
the model understand how to generate proper responses.
"""

# =============================================================================
# CODE GENERATION EXAMPLES
# =============================================================================

CODE_GENERATION_EXAMPLES = [
    {
        "issue": "Add a function to validate email addresses",
        "output": """{
    "files": [
        {
            "path": "src/validators.py",
            "content": "import re\\n\\ndef validate_email(email: str) -> bool:\\n    pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\\\\.[a-zA-Z0-9-.]+$'\\n    return bool(re.match(pattern, email))",
            "action": "modify"
        },
        {
            "path": "tests/test_validators.py",
            "content": "from src.validators import validate_email\\n\\ndef test_validate_email_valid():\\n    assert validate_email('user@example.com') is True\\n\\ndef test_validate_email_invalid():\\n    assert validate_email('invalid-email') is False",
            "action": "modify"
        }
    ],
    "explanation": "Added email validation function with regex pattern and tests"
}"""
    },
    {
        "issue": "Create a hello world endpoint that returns JSON",
        "output": """{
    "files": [
        {
            "path": "src/routes.py",
            "content": "from flask import jsonify\\n\\n@app.route('/hello')\\ndef hello():\\n    return jsonify({'message': 'Hello, World!'})",
            "action": "modify"
        }
    ],
    "explanation": "Added /hello endpoint returning JSON response"
}"""
    },
]


# =============================================================================
# CODE FIX EXAMPLES (based on review feedback)
# =============================================================================

CODE_FIX_EXAMPLES = [
    {
        "feedback": "[ERROR] src/api.py:25 - Missing input validation. User input is used directly without checking for None.",
        "output": """{
    "files": [
        {
            "path": "src/api.py",
            "content": "def process_user(name: str | None) -> str:\\n    if not name:\\n        raise ValueError('Name cannot be empty')\\n    return name.strip().upper()",
            "action": "modify"
        }
    ],
    "explanation": "Added None check and input validation before processing"
}"""
    },
    {
        "feedback": "[ERROR] Missing error handling for database connection failure",
        "output": """{
    "files": [
        {
            "path": "src/db.py",
            "content": "def get_connection():\\n    try:\\n        conn = sqlite3.connect(DB_PATH)\\n        return conn\\n    except sqlite3.Error as e:\\n        logger.error(f'Database connection failed: {e}')\\n        raise DatabaseConnectionError(f'Failed to connect: {e}')",
            "action": "modify"
        }
    ],
    "explanation": "Added try-except block with proper error logging and custom exception"
}"""
    },
]


# =============================================================================
# CI FIX EXAMPLES
# =============================================================================

CI_FIX_EXAMPLES = [
    {
        "error": "ruff check failed:\nsrc/main.py:10:1: E302 expected 2 blank lines, found 1",
        "output": """{
    "files": [
        {
            "path": "src/main.py",
            "content": "import os\\n\\n\\ndef main():\\n    pass",
            "action": "modify"
        }
    ],
    "explanation": "Added missing blank line to comply with PEP8"
}"""
    },
    {
        "error": "pytest failed:\nFAILED tests/test_calc.py::test_add - AssertionError: assert 5 == 4",
        "output": """{
    "files": [
        {
            "path": "src/calc.py",
            "content": "def add(a: int, b: int) -> int:\\n    return a + b  # Fixed: was returning a * b",
            "action": "modify"
        }
    ],
    "explanation": "Fixed add function - was multiplying instead of adding"
}"""
    },
    {
        "error": "mypy error:\nsrc/utils.py:15: error: Incompatible return value type (got 'str', expected 'int')",
        "output": """{
    "files": [
        {
            "path": "src/utils.py",
            "content": "def get_count() -> int:\\n    return int(self._count)  # Fixed: convert to int",
            "action": "modify"
        }
    ],
    "explanation": "Fixed return type by converting string to int"
}"""
    },
]


# =============================================================================
# REVIEW EXAMPLES
# =============================================================================

REVIEW_EXAMPLES = [
    {
        "issue": "Add email validation function",
        "diff": """+def validate_email(email: str) -> bool:
+    import re
+    pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\\.[a-zA-Z0-9-.]+$'
+    return bool(re.match(pattern, email))""",
        "output": """{
    "assessment": "Implementation correctly adds email validation with proper regex",
    "issues": [],
    "requirements_met": true,
    "requirements_notes": "Email validation function implemented as requested",
    "approved": true
}"""
    },
    {
        "issue": "Add user authentication with password hashing",
        "diff": """+def authenticate(username: str, password: str) -> bool:
+    user = db.get_user(username)
+    return user.password == password""",
        "output": """{
    "assessment": "Critical security issue - password stored/compared in plain text",
    "issues": [
        {
            "severity": "error",
            "file_path": "src/auth.py",
            "line": 3,
            "description": "Password compared in plain text - security vulnerability",
            "suggestion": "Use bcrypt.checkpw() to compare hashed passwords"
        }
    ],
    "requirements_met": false,
    "requirements_notes": "Password hashing requirement not implemented",
    "approved": false
}"""
    },
    {
        "issue": "Add logging to the application",
        "diff": """+import logging
+logger = logging.getLogger(__name__)
+
+def process():
+    logger.info('Processing started')
+    # ... existing code ...
+    logger.info('Processing complete')""",
        "output": """{
    "assessment": "Logging implemented correctly with standard library",
    "issues": [],
    "requirements_met": true,
    "requirements_notes": "Logging added as requested",
    "approved": true
}"""
    },
]


# =============================================================================
# FORMATTING FUNCTIONS
# =============================================================================

def format_code_generation_examples() -> str:
    """Format code generation examples for prompt."""
    if not CODE_GENERATION_EXAMPLES:
        return ""

    lines = ["\n--- EXAMPLES ---"]
    for i, ex in enumerate(CODE_GENERATION_EXAMPLES, 1):
        lines.append(f"\nExample {i}:")
        lines.append(f"Issue: {ex['issue']}")
        lines.append(f"Expected output:\n{ex['output']}")
    lines.append("--- END EXAMPLES ---\n")
    return "\n".join(lines)


def format_code_fix_examples() -> str:
    """Format code fix examples for prompt."""
    if not CODE_FIX_EXAMPLES:
        return ""

    lines = ["\n--- EXAMPLES ---"]
    for i, ex in enumerate(CODE_FIX_EXAMPLES, 1):
        lines.append(f"\nExample {i}:")
        lines.append(f"Feedback: {ex['feedback']}")
        lines.append(f"Expected output:\n{ex['output']}")
    lines.append("--- END EXAMPLES ---\n")
    return "\n".join(lines)


def format_ci_fix_examples() -> str:
    """Format CI fix examples for prompt."""
    if not CI_FIX_EXAMPLES:
        return ""

    lines = ["\n--- EXAMPLES ---"]
    for i, ex in enumerate(CI_FIX_EXAMPLES, 1):
        lines.append(f"\nExample {i}:")
        lines.append(f"CI Error: {ex['error']}")
        lines.append(f"Expected output:\n{ex['output']}")
    lines.append("--- END EXAMPLES ---\n")
    return "\n".join(lines)


def format_review_examples() -> str:
    """Format review examples for prompt."""
    if not REVIEW_EXAMPLES:
        return ""

    lines = ["\n--- EXAMPLES ---"]
    for i, ex in enumerate(REVIEW_EXAMPLES, 1):
        lines.append(f"\nExample {i}:")
        lines.append(f"Issue requirement: {ex['issue']}")
        lines.append(f"Diff:\n{ex['diff']}")
        lines.append(f"Expected review:\n{ex['output']}")
    lines.append("--- END EXAMPLES ---\n")
    return "\n".join(lines)
