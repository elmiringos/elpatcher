"""Onboarding module for new repository installations."""

import logging
from pathlib import Path

from patcher.server.github_app import get_github_app_auth
from patcher.github.client import GitHubClient

logger = logging.getLogger(__name__)

# Path to workflow template
WORKFLOW_TEMPLATE_PATH = Path(__file__).parent / "templates" / "elpatcher.yaml"

# Workflow file path in target repository
WORKFLOW_TARGET_PATH = ".github/workflows/elpatcher.yaml"

# Branch name for onboarding PR
ONBOARDING_BRANCH = "elpatcher/onboarding"

PR_TITLE = "🤖 Add ElPatcher AI Review workflow"

PR_BODY = """## Добро пожаловать в ElPatcher!

Этот PR добавляет GitHub Actions workflow для автоматического AI code review.

### Как это работает?

```
PR создан → [Ваш CI, если есть] → ElPatcher Review → ✅/❌
```

- **Зелёный статус** = PR одобрен AI
- **Красный статус** = AI запросил изменения (см. комментарии)

**Никаких секретов не требуется!** LLM ключи хранятся на ElPatcher сервере.

### Что делает ElPatcher?

- Если есть CI workflows — ждёт их завершения
- Если CI нет — запускается сразу при создании PR
- Анализирует изменения кода с помощью AI
- Сравнивает реализацию с описанием Issue
- Публикует детальные review комментарии
- Устанавливает статус workflow (approved/changes requested)

### Два режима работы

**1. Code Agent (генерация кода)**
- Создайте Issue с меткой `elpatcher`
- AI автоматически создаст PR с реализацией
- PR получит метки `ai-review` и `elpatcher`

**2. Review Agent (ревью PR)**

Добавьте метку `ai-review` или `elpatcher` к любому PR.

Или создайте PR из ветки `elpatcher/*`.

### Итеративный цикл

Если AI Review запросил изменения:
1. AI автоматически опубликует комментарий с `@elpatcher fix`
2. Coding Agent исправит код
3. Review Agent проверит снова
4. Цикл повторяется до успеха (макс. 5 итераций)

### Начало работы

1. **Смержите этот PR**
2. Создайте Issue с меткой `elpatcher` — AI создаст PR
3. Или добавьте метку `ai-review` к существующему PR

---
*Этот PR создан автоматически при установке [ElPatcher AI Agent](https://github.com/elpatcher/elpatcher)*
"""

COMMIT_MESSAGE = """Add ElPatcher AI Review workflow

This workflow enables automatic AI code review for Pull Requests.

Features:
- Runs after CI checks complete
- Analyzes code changes with AI
- Compares implementation with Issue requirements
- Posts detailed review comments
"""


def get_workflow_content() -> str:
    """Get the workflow template content.

    Returns:
        Workflow YAML content
    """
    if WORKFLOW_TEMPLATE_PATH.exists():
        return WORKFLOW_TEMPLATE_PATH.read_text()

    # Fallback minimal workflow
    return """name: ElPatcher AI Review

on:
  check_suite:
    types: [completed]
  pull_request:
    types: [opened, synchronize]

permissions:
  contents: read
  pull-requests: write
  checks: read

env:
  ELPATCHER_API_URL: https://api.elpatcher.dev

jobs:
  patcher-review:
    if: |
      (github.event_name == 'check_suite' &&
       github.event.check_suite.conclusion == 'success' &&
       github.event.check_suite.pull_requests[0] != null) ||
      github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - name: ElPatcher AI Review
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          if [ "${{ github.event_name }}" = "check_suite" ]; then
            PR_NUMBER="${{ github.event.check_suite.pull_requests[0].number }}"
          else
            PR_NUMBER="${{ github.event.pull_request.number }}"
          fi

          PR_DATA=$(gh api repos/${{ github.repository }}/pulls/$PR_NUMBER)
          LABELS=$(echo "$PR_DATA" | jq -r '.labels[].name' | tr '\\n' ',')
          HEAD_REF=$(echo "$PR_DATA" | jq -r '.head.ref')

          # For pull_request: check if other workflows exist
          if [ "${{ github.event_name }}" = "pull_request" ]; then
            sleep 5
            CHECKS=$(gh api repos/${{ github.repository }}/commits/${{ github.event.pull_request.head.sha }}/check-runs \\
              --jq '.check_runs | map(select(.name != "patcher-review")) | length')
            if [ "$CHECKS" -gt 0 ]; then
              echo "Waiting for other checks to complete"
              exit 0
            fi
          fi

          if [[ "$LABELS" != *"ai-review"* ]] && [[ "$LABELS" != *"elpatcher"* ]] && [[ "$HEAD_REF" != elpatcher/* ]]; then
            echo "No ai-review/elpatcher label, skipping"
            exit 0
          fi

          response=$(curl -s -X POST "$ELPATCHER_API_URL/api/review" \\
            -H "Content-Type: application/json" \\
            -H "X-GitHub-Token: $GITHUB_TOKEN" \\
            -d "{\\"pr_number\\": $PR_NUMBER, \\"repo\\": \\"${{ github.repository }}\\"}")
          approved=$(echo "$response" | jq -r '.approved')
          echo "$response" | jq -r '.summary'
          [ "$approved" = "true" ] && exit 0 || exit 1
"""


async def check_workflow_exists(github_client: GitHubClient) -> bool:
    """Check if the patcher workflow already exists.

    Args:
        github_client: GitHub client

    Returns:
        True if workflow exists
    """
    try:
        github_client.get_file_content(WORKFLOW_TARGET_PATH)
        return True
    except Exception:
        return False


async def check_onboarding_pr_exists(github_client: GitHubClient) -> bool:
    """Check if an onboarding PR already exists.

    Args:
        github_client: GitHub client

    Returns:
        True if onboarding PR exists
    """
    try:
        prs = github_client.repo.get_pulls(state="open", head=ONBOARDING_BRANCH)
        return prs.totalCount > 0
    except Exception:
        return False


async def create_onboarding_pr(
    installation_id: int,
    repo_full_name: str,
) -> dict:
    """Create an onboarding PR with the patcher workflow.

    Args:
        installation_id: GitHub App installation ID
        repo_full_name: Repository full name (owner/repo)

    Returns:
        Result dictionary with PR URL or error
    """
    logger.info(f"Creating onboarding PR for {repo_full_name}")

    try:
        # Get authenticated client
        app_auth = get_github_app_auth()
        token = await app_auth.get_installation_token(installation_id)
        github_client = GitHubClient(token=token, repo_name=repo_full_name)

        # Check if workflow already exists
        if await check_workflow_exists(github_client):
            logger.info(f"Workflow already exists in {repo_full_name}")
            return {
                "status": "skipped",
                "reason": "workflow_exists",
            }

        # Check if onboarding PR already exists
        if await check_onboarding_pr_exists(github_client):
            logger.info(f"Onboarding PR already exists in {repo_full_name}")
            return {
                "status": "skipped",
                "reason": "pr_exists",
            }

        # Get default branch
        repo = github_client.repo
        default_branch = repo.default_branch

        # Create branch
        try:
            github_client.create_branch(ONBOARDING_BRANCH, default_branch)
        except Exception as e:
            if "Reference already exists" in str(e):
                logger.info(f"Branch {ONBOARDING_BRANCH} already exists")
            else:
                raise

        # Get workflow content
        workflow_content = get_workflow_content()

        # Commit the workflow file
        github_client.commit_changes(
            files={WORKFLOW_TARGET_PATH: workflow_content},
            message=COMMIT_MESSAGE,
            branch=ONBOARDING_BRANCH,
        )

        # Create PR
        pr = github_client.create_pull_request(
            title=PR_TITLE,
            body=PR_BODY,
            head=ONBOARDING_BRANCH,
            base=default_branch,
            labels=["elpatcher", "onboarding"],
        )

        logger.info(f"Created onboarding PR: {pr.url}")

        return {
            "status": "success",
            "pr_url": pr.url,
            "pr_number": pr.number,
        }

    except Exception as e:
        logger.exception(f"Failed to create onboarding PR for {repo_full_name}")
        return {
            "status": "error",
            "error": str(e),
        }


async def handle_installation_event(payload: dict) -> dict:
    """Handle GitHub App installation event.

    Args:
        payload: Webhook payload

    Returns:
        Result dictionary
    """
    action = payload.get("action")
    installation_id = payload.get("installation", {}).get("id")

    if action == "created":
        # New installation - process all repositories
        repositories = payload.get("repositories", [])
        results = []

        for repo in repositories:
            repo_full_name = repo.get("full_name")
            if repo_full_name:
                result = await create_onboarding_pr(installation_id, repo_full_name)
                results.append({
                    "repository": repo_full_name,
                    **result,
                })

        return {
            "status": "processed",
            "action": action,
            "results": results,
        }

    elif action == "deleted":
        # Installation removed - nothing to do
        return {
            "status": "acknowledged",
            "action": action,
        }

    return {
        "status": "ignored",
        "action": action,
    }


async def handle_installation_repositories_event(payload: dict) -> dict:
    """Handle installation_repositories event (repos added/removed).

    Args:
        payload: Webhook payload

    Returns:
        Result dictionary
    """
    action = payload.get("action")
    installation_id = payload.get("installation", {}).get("id")

    if action == "added":
        # New repositories added to existing installation
        repositories = payload.get("repositories_added", [])
        results = []

        for repo in repositories:
            repo_full_name = repo.get("full_name")
            if repo_full_name:
                result = await create_onboarding_pr(installation_id, repo_full_name)
                results.append({
                    "repository": repo_full_name,
                    **result,
                })

        return {
            "status": "processed",
            "action": action,
            "results": results,
        }

    elif action == "removed":
        # Repositories removed - nothing to do
        return {
            "status": "acknowledged",
            "action": action,
        }

    return {
        "status": "ignored",
        "action": action,
    }
