"""Webhook handlers for GitHub events."""

import hashlib
import hmac
import logging
import re
from dataclasses import dataclass
from enum import Enum

from fastapi import Request, HTTPException

from patcher.server.config import get_settings
from patcher.server.github_app import get_github_app_auth
from patcher.github.client import GitHubClient
from patcher.llm import get_provider
from patcher.agents import CodeAgent, AgentContext


logger = logging.getLogger(__name__)

# Runtime storage for iteration counts per PR
# Format: {"owner/repo#pr_number": iteration_count}
_pr_iteration_counts: dict[str, int] = {}

# Runtime storage to prevent duplicate issue processing
# Format: {"owner/repo#issue_number": True}
_processing_issues: dict[str, bool] = {}


def get_issue_processing_key(repo: str, issue_number: int) -> str:
    """Generate key for issue processing tracking."""
    return f"{repo}#issue-{issue_number}"


def is_issue_processing(repo: str, issue_number: int) -> bool:
    """Check if issue is already being processed."""
    key = get_issue_processing_key(repo, issue_number)
    return _processing_issues.get(key, False)


def mark_issue_processing(repo: str, issue_number: int) -> bool:
    """Mark issue as processing. Returns False if already processing."""
    key = get_issue_processing_key(repo, issue_number)
    if _processing_issues.get(key, False):
        return False
    _processing_issues[key] = True
    return True


def clear_issue_processing(repo: str, issue_number: int) -> None:
    """Clear issue processing flag."""
    key = get_issue_processing_key(repo, issue_number)
    _processing_issues.pop(key, None)


def get_pr_iteration_key(repo: str, pr_number: int) -> str:
    """Generate key for PR iteration tracking."""
    return f"{repo}#{pr_number}"


def get_pr_iteration_count(repo: str, pr_number: int) -> int:
    """Get current iteration count for a PR."""
    key = get_pr_iteration_key(repo, pr_number)
    return _pr_iteration_counts.get(key, 0)


def increment_pr_iteration(repo: str, pr_number: int) -> int:
    """Increment and return iteration count for a PR."""
    key = get_pr_iteration_key(repo, pr_number)
    _pr_iteration_counts[key] = _pr_iteration_counts.get(key, 0) + 1
    return _pr_iteration_counts[key]


def reset_pr_iteration(repo: str, pr_number: int) -> None:
    """Reset iteration count for a PR (e.g., when PR is merged/closed)."""
    key = get_pr_iteration_key(repo, pr_number)
    _pr_iteration_counts.pop(key, None)


class WebhookEvent(str, Enum):
    """Supported webhook events."""

    ISSUES = "issues"
    ISSUE_COMMENT = "issue_comment"
    PULL_REQUEST = "pull_request"
    PULL_REQUEST_REVIEW = "pull_request_review"
    CHECK_RUN = "check_run"
    INSTALLATION = "installation"
    INSTALLATION_REPOSITORIES = "installation_repositories"


# Pattern to detect coding agent mentions in comments
ELPATCHER_MENTION_PATTERN = re.compile(
    r"(?:@elpatcher|/elpatcher)\s*(?:fix|исправь|исправить)?",
    re.IGNORECASE,
)


@dataclass
class WebhookPayload:
    """Parsed webhook payload."""

    event: str
    action: str
    installation_id: int
    repository: str
    sender: str
    data: dict


async def verify_webhook_signature(request: Request, body: bytes) -> bool:
    """Verify the webhook signature from GitHub.

    Args:
        request: FastAPI request
        body: Raw request body

    Returns:
        True if signature is valid

    Raises:
        HTTPException: If signature is invalid
    """
    settings = get_settings()

    if not settings.github_webhook_secret:
        logger.warning("Webhook secret not configured, skipping verification")
        return True

    signature_header = request.headers.get("X-Hub-Signature-256", "")
    if not signature_header:
        raise HTTPException(status_code=401, detail="Missing signature header")

    # Calculate expected signature
    expected_signature = (
        "sha256="
        + hmac.new(
            settings.github_webhook_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
    )

    if not hmac.compare_digest(signature_header, expected_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    return True


def parse_webhook_payload(event_type: str, payload: dict) -> WebhookPayload:
    """Parse a webhook payload into a structured format.

    Args:
        event_type: GitHub event type
        payload: Raw payload dictionary

    Returns:
        Parsed WebhookPayload
    """
    return WebhookPayload(
        event=event_type,
        action=payload.get("action", ""),
        installation_id=payload.get("installation", {}).get("id", 0),
        repository=payload.get("repository", {}).get("full_name", ""),
        sender=payload.get("sender", {}).get("login", ""),
        data=payload,
    )


async def handle_issue_event(payload: WebhookPayload) -> dict:
    """Handle issue events.

    Args:
        payload: Webhook payload

    Returns:
        Result dictionary
    """
    settings = get_settings()
    issue = payload.data.get("issue", {})
    issue_number = issue.get("number")
    labels = [label.get("name") for label in issue.get("labels", [])]

    # Only process issues with 'elpatcher' label
    if "elpatcher" not in labels:
        logger.info(f"Skipping issue #{issue_number} - no 'elpatcher' label")
        return {"status": "skipped", "reason": "missing elpatcher label"}

    if payload.action not in ["opened", "labeled"]:
        logger.info(f"Skipping issue #{issue_number} - action: {payload.action}")
        return {"status": "skipped", "reason": f"unsupported action: {payload.action}"}

    # Prevent duplicate processing (opened + labeled events can fire together)
    if not mark_issue_processing(payload.repository, issue_number):
        logger.info(f"Skipping issue #{issue_number} - already being processed")
        return {"status": "skipped", "reason": "already processing"}

    logger.info(f"Processing issue #{issue_number} in {payload.repository}")

    try:
        # Get GitHub client for this installation
        app_auth = get_github_app_auth()
        token = await app_auth.get_installation_token(payload.installation_id)

        github_client = GitHubClient(token=token, repo_name=payload.repository)
        llm_provider = get_provider(provider_name=settings.llm_provider)

        context = AgentContext(
            github_client=github_client,
            llm_provider=llm_provider,
            max_iterations=settings.max_iterations,
        )

        agent = CodeAgent(context)
        result = await agent.run(issue_number=issue_number)

        if result.success:
            logger.info(f"Successfully processed issue #{issue_number}: {result.pr_url}")
            return {
                "status": "success",
                "pr_url": result.pr_url,
                "iteration_count": result.iteration_count,
            }
        else:
            logger.error(f"Failed to process issue #{issue_number}: {result.error}")
            return {"status": "error", "error": result.error}

    except Exception as e:
        logger.exception(f"Error processing issue #{issue_number}")
        return {"status": "error", "error": str(e)}

    finally:
        clear_issue_processing(payload.repository, issue_number)


async def handle_pull_request_event(payload: WebhookPayload) -> dict:
    """Handle pull request events.

    NOTE: Reviews are handled by GitHub Actions workflow via /api/review endpoint.
    Webhook does NOT run ReviewAgent directly to avoid "can't approve own PR" issue.

    Args:
        payload: Webhook payload

    Returns:
        Result dictionary
    """
    pr = payload.data.get("pull_request", {})
    pr_number = pr.get("number")

    # All PR reviews are handled by GitHub Actions workflow, not webhook
    # Workflow calls /api/review endpoint which runs ReviewAgent
    logger.info(f"PR #{pr_number} event received - review handled by workflow")
    return {"status": "skipped", "reason": "reviews handled by workflow"}


async def handle_pull_request_review_event(payload: WebhookPayload) -> dict:
    """Handle pull request review events (for iteration).

    Args:
        payload: Webhook payload

    Returns:
        Result dictionary
    """
    settings = get_settings()
    review = payload.data.get("review", {})
    pr = payload.data.get("pull_request", {})
    pr_number = pr.get("number")
    head_ref = pr.get("head", {}).get("ref", "")

    # Only handle reviews on patcher PRs
    if not head_ref.startswith("elpatcher/"):
        return {"status": "skipped", "reason": "not a patcher PR"}

    # Only handle "changes_requested" reviews
    if review.get("state") != "changes_requested":
        return {"status": "skipped", "reason": "not a changes_requested review"}

    logger.info(f"Processing review feedback for PR #{pr_number}")

    try:
        # Get GitHub client
        app_auth = get_github_app_auth()
        token = await app_auth.get_installation_token(payload.installation_id)

        github_client = GitHubClient(token=token, repo_name=payload.repository)
        llm_provider = get_provider(provider_name=settings.llm_provider)

        # Load state from PR
        from patcher.state import StateManager

        state_manager = StateManager(github_client)
        state = state_manager.load_from_pr(pr_number)

        if not state:
            return {"status": "skipped", "reason": "no patcher state found"}

        if state.iteration_count >= settings.max_iterations:
            logger.warning(f"PR #{pr_number} reached max iterations")
            return {"status": "max_iterations_reached"}

        context = AgentContext(
            github_client=github_client,
            llm_provider=llm_provider,
            max_iterations=settings.max_iterations,
        )

        agent = CodeAgent(context)
        result = await agent.iterate(pr_number=pr_number, state=state)

        return {
            "status": "success" if result.success else "error",
            "iteration_count": result.iteration_count,
            "error": result.error,
        }

    except Exception as e:
        logger.exception(f"Error iterating on PR #{pr_number}")
        return {"status": "error", "error": str(e)}


async def handle_issue_comment_event(payload: WebhookPayload) -> dict:
    """Handle issue_comment events for triggering coding agent.

    Coding agent is triggered when someone comments with @elpatcher or /elpatcher
    on a PR with elpatcher label.

    Args:
        payload: Webhook payload

    Returns:
        Result dictionary
    """
    settings = get_settings()

    # Only handle created comments
    if payload.action != "created":
        return {"status": "skipped", "reason": f"unsupported action: {payload.action}"}

    comment = payload.data.get("comment", {})
    comment_body = comment.get("body", "")
    issue = payload.data.get("issue", {})

    # Check if this is a PR (issue_comment fires for both issues and PRs)
    if "pull_request" not in issue:
        return {"status": "skipped", "reason": "not a pull request"}

    pr_number = issue.get("number")
    labels = [label.get("name") for label in issue.get("labels", [])]

    # Only process PRs with 'elpatcher' or 'ai-review' labels
    if "elpatcher" not in labels and "ai-review" not in labels:
        return {"status": "skipped", "reason": "no elpatcher/ai-review label"}

    # Check if comment mentions elpatcher
    if not ELPATCHER_MENTION_PATTERN.search(comment_body):
        return {"status": "skipped", "reason": "no elpatcher mention"}

    # Check iteration limit
    current_iterations = get_pr_iteration_count(payload.repository, pr_number)
    if current_iterations >= settings.max_iterations:
        logger.warning(
            f"PR #{pr_number} in {payload.repository} reached max iterations "
            f"({current_iterations}/{settings.max_iterations}), skipping"
        )

        # Post comment about max iterations reached
        try:
            app_auth = get_github_app_auth()
            token = await app_auth.get_installation_token(payload.installation_id)
            github_client = GitHubClient(token=token, repo_name=payload.repository)

            max_iterations_comment = f"""## ⚠️ Достигнут лимит итераций

ElPatcher AI Agent достиг максимального количества итераций ({settings.max_iterations}).

**Что это значит:**
- Автоматические исправления больше не будут применяться к этому PR
- Необходимо ручное вмешательство для продолжения

**Возможные действия:**
1. Просмотрите комментарии review и внесите исправления вручную
2. Закройте PR и создайте новый issue с более детальным описанием
3. Обратитесь к maintainer'у проекта

*Лимит итераций можно изменить в настройках сервера (MAX_ITERATIONS)*
"""
            github_client.post_comment(pr_number, max_iterations_comment)
            logger.info(f"Posted max iterations comment to PR #{pr_number}")
        except Exception as e:
            logger.error(f"Failed to post max iterations comment: {e}")

        return {
            "status": "skipped",
            "reason": "max_iterations_reached",
            "iteration_count": current_iterations,
            "max_iterations": settings.max_iterations,
        }

    logger.info(
        f"Coding agent triggered for PR #{pr_number} in {payload.repository} "
        f"(iteration {current_iterations + 1}/{settings.max_iterations})"
    )

    try:
        # Get GitHub client
        app_auth = get_github_app_auth()
        token = await app_auth.get_installation_token(payload.installation_id)

        github_client = GitHubClient(token=token, repo_name=payload.repository)
        llm_provider = get_provider(provider_name=settings.llm_provider)

        # Load state from PR
        from patcher.state import StateManager

        state_manager = StateManager(github_client)
        state = state_manager.load_from_pr(pr_number)

        if not state:
            logger.warning(f"No patcher state found for PR #{pr_number}")
            return {"status": "skipped", "reason": "no patcher state found"}

        # Increment iteration count
        new_iteration = increment_pr_iteration(payload.repository, pr_number)

        context = AgentContext(
            github_client=github_client,
            llm_provider=llm_provider,
            max_iterations=settings.max_iterations,
        )

        agent = CodeAgent(context)
        result = await agent.iterate(pr_number=pr_number, state=state)

        if result.success:
            logger.info(
                f"Coding agent completed iteration {new_iteration} for PR #{pr_number}"
            )
        else:
            logger.error(f"Coding agent failed for PR #{pr_number}: {result.error}")

        return {
            "status": "success" if result.success else "error",
            "iteration_count": new_iteration,
            "error": result.error,
        }

    except Exception as e:
        logger.exception(f"Error running coding agent for PR #{pr_number}")
        return {"status": "error", "error": str(e)}


async def handle_webhook(event_type: str, payload: dict) -> dict:
    """Main webhook handler that routes to specific handlers.

    Args:
        event_type: GitHub event type
        payload: Webhook payload

    Returns:
        Handler result
    """
    parsed = parse_webhook_payload(event_type, payload)

    logger.info(
        f"Received webhook: {event_type}/{parsed.action} "
        f"from {parsed.repository or 'N/A'} by {parsed.sender}"
    )

    if event_type == WebhookEvent.INSTALLATION:
        from patcher.server.onboarding import handle_installation_event
        return await handle_installation_event(payload)

    elif event_type == WebhookEvent.INSTALLATION_REPOSITORIES:
        from patcher.server.onboarding import handle_installation_repositories_event
        return await handle_installation_repositories_event(payload)

    elif event_type == WebhookEvent.ISSUES:
        return await handle_issue_event(parsed)

    elif event_type == WebhookEvent.ISSUE_COMMENT:
        return await handle_issue_comment_event(parsed)

    elif event_type == WebhookEvent.PULL_REQUEST:
        return await handle_pull_request_event(parsed)

    elif event_type == WebhookEvent.PULL_REQUEST_REVIEW:
        return await handle_pull_request_review_event(parsed)

    else:
        logger.debug(f"Ignoring event type: {event_type}")
        return {"status": "ignored", "event": event_type}
