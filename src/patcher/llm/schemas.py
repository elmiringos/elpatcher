"""Pydantic schemas for structured LLM outputs."""

from pydantic import BaseModel, Field


class RequirementsAnalysis(BaseModel):
    """Structured analysis of issue requirements."""

    summary: str = Field(description="One sentence summary of the task")
    tasks: list[str] = Field(description="List of specific tasks to complete")
    files_to_modify: list[str] = Field(
        default_factory=list,
        description="Existing files that need modification",
    )
    files_to_create: list[str] = Field(
        default_factory=list,
        description="New files to create",
    )
    test_requirements: list[str] = Field(
        default_factory=list,
        description="Testing requirements",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="External dependencies needed",
    )


class FileChange(BaseModel):
    """A file change to be made."""

    path: str = Field(description="File path relative to repository root")
    content: str = Field(description="Complete file content")
    action: str = Field(
        default="modify",
        description="Action: 'create', 'modify', or 'delete'",
    )


class ImplementationPlan(BaseModel):
    """Structured implementation plan."""

    approach: str = Field(description="High-level implementation approach")
    steps: list[str] = Field(description="Step-by-step implementation plan")
    risks: list[str] = Field(
        default_factory=list,
        description="Potential risks or challenges",
    )
    testing_strategy: str = Field(
        default="",
        description="How to test the implementation",
    )


class CodeGeneration(BaseModel):
    """Structured code generation output."""

    files: list[FileChange] = Field(description="List of file changes")
    explanation: str = Field(
        default="",
        description="Brief explanation of changes",
    )


class ReviewIssue(BaseModel):
    """A single issue found during code review."""

    severity: str = Field(description="Severity: 'error', 'warning', or 'info'")
    file_path: str = Field(description="File path where issue was found")
    line: int | None = Field(default=None, description="Line number if applicable")
    description: str = Field(description="Description of the issue")
    suggestion: str = Field(default="", description="Suggested fix")


class CodeReview(BaseModel):
    """Structured code review output."""

    assessment: str = Field(description="Overall assessment of the changes")
    issues: list[ReviewIssue] = Field(
        default_factory=list,
        description="List of issues found",
    )
    requirements_met: bool = Field(
        description="Whether implementation meets requirements",
    )
    requirements_notes: str = Field(
        default="",
        description="Notes about requirements matching",
    )
    approved: bool = Field(description="Whether the PR should be approved")


class CIAnalysis(BaseModel):
    """Structured CI failure analysis."""

    passed: bool = Field(description="Whether CI passed")
    failures: list[str] = Field(
        default_factory=list,
        description="List of failed checks",
    )
    root_causes: list[str] = Field(
        default_factory=list,
        description="Root causes of failures",
    )
    suggested_fixes: list[str] = Field(
        default_factory=list,
        description="Suggested fixes for failures",
    )
