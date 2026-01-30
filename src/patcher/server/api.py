"""API endpoints for synchronous operations from GitHub Actions."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel

from patcher.server.config import get_settings
from patcher.github.client import GitHubClient
from patcher.llm import get_provider
from patcher.agents import ReviewAgent
from patcher.agents.base import AgentContext


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["api"])


class ReviewRequest(BaseModel):
    """Request body for PR review."""

    pr_number: int
    repo: str
    head_sha: Optional[str] = None
    base_ref: Optional[str] = None


class ReviewComment(BaseModel):
    """A review comment for a specific file/line."""

    path: str
    line: int
    body: str


class ReviewResponse(BaseModel):
    """Response body for PR review.

    The workflow should use this data to post the actual review
    using GITHUB_TOKEN (which allows REQUEST_CHANGES on bot PRs).
    """

    status: str  # "success" or "error"
    approved: bool
    summary: str
    review_body: str  # Full formatted review body for gh pr review
    comments: list[ReviewComment] = []  # Inline comments
    issues_count: int = 0
    errors_count: int = 0
    warnings_count: int = 0


async def verify_github_token(
    authorization: Optional[str] = Header(None),
    x_github_token: Optional[str] = Header(None),
) -> str:
    """Extract and verify GitHub token from headers.

    Accepts token in either:
    - Authorization: Bearer <token>
    - X-GitHub-Token: <token>
    """
    token = None

    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    elif x_github_token:
        token = x_github_token

    if not token:
        raise HTTPException(
            status_code=401,
            detail="GitHub token required. Use 'Authorization: Bearer <token>' or 'X-GitHub-Token: <token>'"
        )

    return token


@router.post("/review", response_model=ReviewResponse)
async def review_pr(
    request: ReviewRequest,
    github_token: str = Depends(verify_github_token),
) -> ReviewResponse:
    """Synchronous PR review endpoint for GitHub Actions.

    Analyzes PR and returns review data.
    Does NOT post review - the workflow should post using GITHUB_TOKEN.

    The workflow should:
    1. Call this endpoint to get review analysis
    2. Post review using: gh pr review --request-changes --body "$review_body"
    3. Exit 0 if approved, exit 1 if changes requested
    """
    settings = get_settings()

    logger.info(f"Sync review request for PR #{request.pr_number} in {request.repo}")

    try:
        github_client = GitHubClient(token=github_token, repo_name=request.repo)
        llm_provider = get_provider(provider_name=settings.llm_provider)

        context = AgentContext(
            github_client=github_client,
            llm_provider=llm_provider,
            max_iterations=settings.max_iterations,
        )

        agent = ReviewAgent(context)
        result = await agent.run(
            pr_number=request.pr_number,
            wait_for_ci=False,  # Don't wait for CI
            check_ci=False,     # Don't check CI (workflow handles this)
            post_review=False,  # Don't post - workflow will post with GITHUB_TOKEN
        )

        # Count issues by severity
        errors_count = sum(1 for s in result.suggestions if s.severity == "error")
        warnings_count = sum(1 for s in result.suggestions if s.severity == "warning")

        # Format review body for the workflow
        if result.approved:
            review_body = f"""## ✅ AI Review: Approved

{result.summary}
"""
        else:
            review_body = f"""## 🔴 AI Review: Changes Requested

{result.summary}

---
@patcher fix - автоматически применить исправления
"""

        # Convert comments to response format
        comments = [
            ReviewComment(path=c.path, line=c.line, body=c.body)
            for c in result.comments
            if c.path and c.line
        ]

        logger.info(
            f"Review analysis complete for PR #{request.pr_number}: "
            f"approved={result.approved}, errors={errors_count}, warnings={warnings_count}"
        )

        return ReviewResponse(
            status="success",
            approved=result.approved,
            summary=result.summary,
            review_body=review_body,
            comments=comments,
            issues_count=len(result.suggestions),
            errors_count=errors_count,
            warnings_count=warnings_count,
        )

    except Exception as e:
        logger.exception(f"Review failed for PR #{request.pr_number}")
        raise HTTPException(
            status_code=500,
            detail=f"Review failed: {str(e)}"
        )


@router.get("/health")
async def api_health():
    """API health check."""
    settings = get_settings()
    return {
        "status": "healthy",
        "llm_provider": settings.llm_provider,
    }
