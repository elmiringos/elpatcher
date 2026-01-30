"""Review Agent for PR analysis and feedback using LangChain."""

from dataclasses import dataclass, field

from langchain_core.messages import HumanMessage

from patcher.agents.base import BaseAgent, AgentContext
from patcher.github.models import IssueData, PRData, CIResult, CIStatus, ReviewComment
from patcher.llm.schemas import CodeReview, CIAnalysis as CIAnalysisSchema
from patcher.prompts import format_review_examples
from patcher.state.models import IterationStatus
from patcher.state.manager import StateManager


@dataclass
class CodeSuggestion:
    """A code improvement suggestion."""

    path: str
    line: int | None
    suggestion: str
    severity: str = "info"  # "info", "warning", "error"


@dataclass
class CIAnalysis:
    """Analysis of CI results."""

    passed: bool
    summary: str
    failures: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass
class ReviewResult:
    """Result of PR review."""

    approved: bool
    summary: str
    comments: list[ReviewComment] = field(default_factory=list)
    suggestions: list[CodeSuggestion] = field(default_factory=list)
    ci_analysis: CIAnalysis | None = None


class ReviewAgent(BaseAgent):
    """Agent that reviews PRs and provides feedback using LangChain."""

    SYSTEM_PROMPT = """You are a strict code reviewer. Your PRIMARY task is to verify that the PR solves the related issue.

Guidelines:
1. MAIN CRITERION: Does the implementation solve the issue requirements?
2. Only report issues that BLOCK the issue from being solved
3. DO NOT report style suggestions, minor optimizations, or "nice to have" improvements
4. If the issue is solved and there are no critical bugs/security issues - APPROVE

Severity levels (use sparingly):
- error: Blocks issue resolution (critical bugs, security vulnerabilities, missing requirements)
- warning: May affect issue resolution (potential bugs that impact functionality)

DO NOT use 'info' severity - we don't want style suggestions.

IMPORTANT: If the PR contains changes to GitHub Actions workflows (.github/workflows/*) or CI/CD configuration files, flag this as an error - automated agents should not modify CI/CD pipelines."""

    def __init__(self, context: AgentContext):
        """Initialize the review agent."""
        super().__init__(context)
        self.state_manager = StateManager(self.github)

        # Create chains for different tasks
        self._review_chain = self.llm.create_structured_chain(
            system_prompt=self.SYSTEM_PROMPT,
            output_schema=CodeReview,
        )
        self._ci_chain = self.llm.create_structured_chain(
            system_prompt=self.SYSTEM_PROMPT,
            output_schema=CIAnalysisSchema,
        )

    async def run(
        self,
        pr_number: int,
        issue_number: int | None = None,
        wait_for_ci: bool = False,
        check_ci: bool = True,
        post_review: bool = True,
    ) -> ReviewResult:
        """Review a PR and provide feedback.

        Args:
            pr_number: PR number to review
            issue_number: Related issue number (optional)
            wait_for_ci: Whether to wait for CI checks to complete
            check_ci: Whether to analyze CI results
            post_review: Whether to post review to PR

        Returns:
            ReviewResult with review outcome
        """
        try:
            # Fetch PR details
            self._log_info(f"Fetching PR #{pr_number}")
            pr = self.github.get_pr(pr_number)
            diff = self.github.get_pr_diff(pr_number)

            # Fetch related issue if provided
            issue = None
            if issue_number:
                issue = self.github.get_issue(issue_number)
            else:
                # Try to extract from PR body
                issue = self._extract_issue_from_pr(pr)

            # Wait for CI if requested
            ci_analysis = None
            if wait_for_ci:
                self._log_info("Waiting for CI checks to complete...")
                ci_result = await self._wait_for_ci(pr_number)
                if check_ci:
                    ci_analysis = await self._analyze_ci(ci_result)
            elif check_ci:
                self._log_info("Checking CI status")
                ci_result = self.github.get_ci_status(pr_number)
                ci_analysis = await self._analyze_ci(ci_result)

            # Analyze the diff using structured output
            self._log_info("Analyzing code changes")
            review = await self._analyze_diff(diff, pr, issue)

            # Determine approval
            ci_passed = ci_analysis.passed if ci_analysis else True
            approved = review.approved and ci_passed

            # Build comments from issues
            comments = [
                ReviewComment(
                    body=f"[{issue.severity.upper()}] {issue.description}",
                    path=issue.file_path if issue.file_path else None,
                    line=issue.line,
                )
                for issue in review.issues
                if issue.file_path
            ]

            # Build suggestions
            suggestions = [
                CodeSuggestion(
                    path=issue.file_path,
                    line=issue.line,
                    suggestion=issue.suggestion,
                    severity=issue.severity,
                )
                for issue in review.issues
                if issue.suggestion
            ]

            # Build summary
            summary = self._build_summary(review, ci_analysis)

            result = ReviewResult(
                approved=approved,
                summary=summary,
                comments=comments,
                suggestions=suggestions,
                ci_analysis=ci_analysis,
            )

            # Post review if requested
            if post_review:
                self._log_info("Posting review")
                await self._post_review(pr_number, result)

            # Update state if exists
            state = self.state_manager.load_from_pr(pr_number)
            if state and state.current_iteration:
                status = (
                    IterationStatus.COMPLETED
                    if approved
                    else IterationStatus.NEEDS_CHANGES
                )
                state.current_iteration.status = status
                state.current_iteration.review_feedback = summary
                if ci_analysis:
                    state.current_iteration.ci_status = (
                        "passed" if ci_analysis.passed else "failed"
                    )
                self.state_manager.save_to_pr(pr_number, state)

            return result

        except Exception as e:
            error_msg = str(e) if e else "Unknown error"
            self.logger.exception(f"Review agent failed: {error_msg}")
            return ReviewResult(
                approved=False,
                summary=f"Review failed: {error_msg}",
            )

    async def _wait_for_ci(
        self,
        pr_number: int,
        timeout_seconds: int = 600,
        poll_interval: int = 30,
    ) -> CIResult:
        """Wait for CI checks to complete.

        Args:
            pr_number: PR number
            timeout_seconds: Maximum time to wait (default 10 minutes)
            poll_interval: Seconds between status checks

        Returns:
            CIResult when checks complete

        Raises:
            TimeoutError: If checks don't complete in time
        """
        import asyncio
        import time

        start_time = time.time()

        while True:
            ci_result = self.github.get_ci_status(pr_number)

            # Check if all checks are complete
            pending = [
                c for c in ci_result.checks
                if c.status == CIStatus.PENDING
            ]

            if not pending:
                self._log_info(f"CI checks complete: {ci_result.status.value}")
                return ci_result

            elapsed = time.time() - start_time
            if elapsed >= timeout_seconds:
                self._log_warning(f"CI timeout after {elapsed:.0f}s, {len(pending)} checks still pending")
                return ci_result

            self._log_info(f"Waiting for {len(pending)} CI check(s)... ({elapsed:.0f}s elapsed)")
            await asyncio.sleep(poll_interval)

    def _extract_issue_from_pr(self, pr: PRData) -> IssueData | None:
        """Try to extract related issue from PR body.

        Args:
            pr: PR data

        Returns:
            IssueData if found, None otherwise
        """
        import re

        # Look for "Resolves #123" or similar patterns
        patterns = [
            r"[Rr]esolves?\s+#(\d+)",
            r"[Ff]ixes?\s+#(\d+)",
            r"[Cc]loses?\s+#(\d+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, pr.body)
            if match:
                issue_number = int(match.group(1))
                try:
                    return self.github.get_issue(issue_number)
                except Exception as e:
                    # Token may not have issues permission (e.g., GITHUB_TOKEN from workflow)
                    self._log_warning(f"Could not fetch issue #{issue_number}: {e}")

        return None

    # CI workflow names that belong to patcher (case-insensitive matching)
    PATCHER_CI_PATTERNS = ["elpatcher", "patcher", "ai-review"]

    def _is_patcher_ci(self, check_name: str) -> bool:
        """Check if a CI check belongs to patcher workflows.

        Args:
            check_name: Name of the CI check

        Returns:
            True if this is a patcher-related check
        """
        check_lower = check_name.lower()
        return any(pattern in check_lower for pattern in self.PATCHER_CI_PATTERNS)

    async def _analyze_ci(
        self,
        ci_result: CIResult,
        patcher_only: bool = True,
    ) -> CIAnalysis:
        """Analyze CI results using structured output.

        Args:
            ci_result: CI result from GitHub
            patcher_only: If True, only analyze patcher-related CI checks

        Returns:
            CIAnalysis with details
        """
        # Filter checks if patcher_only
        if patcher_only:
            relevant_checks = [
                check for check in ci_result.checks
                if self._is_patcher_ci(check.name)
            ]
        else:
            relevant_checks = ci_result.checks

        failures = []
        for check in relevant_checks:
            if check.status == CIStatus.FAILURE:
                failures.append(f"{check.name}: {check.output or 'Failed'}")

        # Determine passed status based on failures only
        # If no explicit failures, consider CI passed (pending/completed = ok)
        if not relevant_checks:
            passed = True  # No patcher CI checks = passed
        else:
            # Only fail if there are actual failures, not pending checks
            passed = len(failures) == 0

        if not passed and failures:
            # Use LLM to analyze failures and suggest fixes
            prompt = f"""Analyze these CI failures and suggest fixes:

{chr(10).join(failures)}

Determine:
1. Whether CI passed overall
2. List of failures
3. Root causes of each failure
4. Specific suggestions to fix each failure"""

            result = await self._ci_chain.ainvoke({
                "messages": [HumanMessage(content=prompt)],
            })

            return CIAnalysis(
                passed=result.passed,
                summary=f"{len(failures)} CI check(s) failed",
                failures=result.failures,
                suggestions=result.suggested_fixes,
            )

        # Determine summary based on actual state
        if not relevant_checks:
            summary = "No patcher CI checks found" if patcher_only else "No CI checks found"
        elif failures:
            summary = f"{len(failures)} patcher check(s) failed" if patcher_only else f"{len(failures)} check(s) failed"
        elif passed:
            summary = "CI checks passed"
        else:
            summary = "CI checks completed"

        return CIAnalysis(
            passed=passed,
            summary=summary,
            failures=failures,
        )

    async def _analyze_diff(
        self,
        diff: str,
        pr: PRData,
        issue: IssueData | None,
    ) -> CodeReview:
        """Analyze the PR diff using structured output.

        Args:
            diff: PR diff
            pr: PR data
            issue: Related issue data (optional)

        Returns:
            Structured code review
        """
        issue_context = ""
        if issue:
            issue_context = f"""
Related Issue: #{issue.number} - {issue.title}
{issue.body}
"""

        few_shot = format_review_examples()

        prompt = f"""Review this pull request diff STRICTLY against the related issue.

PR Title: {pr.title}
PR Description: {pr.body}
{issue_context}

Diff:
```diff
{diff[:10000]}
```
{few_shot}
STRICT REVIEW CRITERIA:
1. Does this PR FULLY solve the issue requirements? List each requirement and whether it's met.
2. Are there any CRITICAL bugs that would break the implementation?
3. Are there any SECURITY vulnerabilities?

DO NOT REPORT:
- Style suggestions
- Performance optimizations (unless critical)
- "Nice to have" improvements
- Code that works but could be "better"

APPROVAL RULE:
- If issue requirements are met AND no critical bugs/security issues → APPROVE
- Only reject if issue is NOT solved or has critical problems

For issues found (ONLY critical ones), specify:
- severity: 'error' or 'warning' (NO 'info')
- file_path: the file where the issue was found
- line: line number if applicable
- description: what the issue is
- suggestion: how to fix it"""

        try:
            result = await self._review_chain.ainvoke({
                "messages": [HumanMessage(content=prompt)],
            })
            return result
        except Exception as e:
            # Fallback if structured output parsing fails (e.g., invalid unicode escapes)
            self._log_warning(f"Structured output failed: {e}, using fallback review")
            return CodeReview(
                assessment="Unable to parse structured review output",
                issues=[],
                requirements_met=True,
                requirements_notes=str(e),
                approved=True,  # Default to approve if parsing fails
            )

    def _build_summary(
        self,
        review: CodeReview,
        ci_analysis: CIAnalysis | None,
    ) -> str:
        """Build review summary.

        Args:
            review: Code review results
            ci_analysis: CI analysis results

        Returns:
            Summary string
        """
        parts = []

        # Assessment
        parts.append(f"**Assessment**: {review.assessment}")

        # Requirements
        if review.requirements_met:
            parts.append("✅ Requirements met")
        else:
            parts.append("❌ Requirements not fully met")
            if review.requirements_notes:
                parts.append(f"   {review.requirements_notes}")

        # CI status
        if ci_analysis:
            if ci_analysis.passed:
                parts.append(f"✅ CI: {ci_analysis.summary}")
            else:
                parts.append(f"❌ CI failed: {ci_analysis.summary}")
                if ci_analysis.suggestions:
                    parts.append("**Suggested fixes:**")
                    for suggestion in ci_analysis.suggestions[:3]:
                        parts.append(f"  - {suggestion}")

        # Issues count
        errors = sum(1 for i in review.issues if i.severity == "error")
        warnings = sum(1 for i in review.issues if i.severity == "warning")

        if errors:
            parts.append(f"❌ {errors} error(s) found")
        if warnings:
            parts.append(f"⚠️ {warnings} warning(s) found")

        if review.approved:
            parts.append("\n✅ **Approved for merge**")
        else:
            parts.append("\n❌ **Changes requested**")

        return "\n".join(parts)

    async def _post_review(self, pr_number: int, result: ReviewResult) -> None:
        """Post review to PR.

        Note: For patcher-created PRs, use the workflow to post reviews
        with GITHUB_TOKEN to enable REQUEST_CHANGES.

        Args:
            pr_number: PR number
            result: Review result
        """
        # Use COMMENT for all reviews posted via GitHub App
        # REQUEST_CHANGES should be posted by workflow using GITHUB_TOKEN
        if result.approved:
            event = "APPROVE"
        else:
            event = "COMMENT"  # Fallback - workflow should handle REQUEST_CHANGES

        # Prepare inline comments
        comments = []
        for comment in result.comments:
            if comment.path and comment.line:
                comments.append(comment)

        self.github.post_review(
            pr_number=pr_number,
            body=result.summary,
            event=event,
            comments=comments if comments else None,
        )
