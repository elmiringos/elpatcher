"""State manager for persisting agent state."""

import json
import re

from patcher.github.client import GitHubClient
from patcher.state.models import AgentState


STATE_MARKER_START = "<!-- PATCHER_STATE_START"
STATE_MARKER_END = "PATCHER_STATE_END -->"


class StateManager:
    """Manages agent state persistence in PR descriptions."""

    def __init__(self, github_client: GitHubClient):
        """Initialize state manager.

        Args:
            github_client: GitHub client for API operations
        """
        self.github = github_client

    def save_to_pr(self, pr_number: int, state: AgentState) -> None:
        """Save state to PR description.

        Args:
            pr_number: PR number
            state: Agent state to save
        """
        pr = self.github.get_pr(pr_number)
        body = pr.body or ""

        # Create state block with ensure_ascii=False for proper unicode handling
        state_json = json.dumps(state.to_dict(), indent=2, ensure_ascii=False)
        state_block = f"{STATE_MARKER_START}\n{state_json}\n{STATE_MARKER_END}"

        # Replace existing state or append
        pattern = rf"{re.escape(STATE_MARKER_START)}.*?{re.escape(STATE_MARKER_END)}"
        if re.search(pattern, body, re.DOTALL):
            new_body = re.sub(pattern, state_block, body, flags=re.DOTALL)
        else:
            new_body = f"{body}\n\n{state_block}"

        self.github.update_pr(pr_number, body=new_body)

    def load_from_pr(self, pr_number: int) -> AgentState | None:
        """Load state from PR description.

        Args:
            pr_number: PR number

        Returns:
            AgentState if found, None otherwise
        """
        pr = self.github.get_pr(pr_number)
        body = pr.body

        # Extract state block
        pattern = rf"{re.escape(STATE_MARKER_START)}\n(.*?)\n{re.escape(STATE_MARKER_END)}"
        match = re.search(pattern, body, re.DOTALL)
        if not match:
            return None

        try:
            state_json = match.group(1)
            data = json.loads(state_json)
            return AgentState.from_dict(data)
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    def update_iteration_status(
        self,
        pr_number: int,
        status: str,
        feedback: str | None = None,
        ci_status: str | None = None,
    ) -> None:
        """Update the current iteration status.

        Args:
            pr_number: PR number
            status: New status
            feedback: Review feedback
            ci_status: CI status
        """
        state = self.load_from_pr(pr_number)
        if not state or not state.current_iteration:
            return

        from patcher.state.models import IterationStatus

        state.current_iteration.status = IterationStatus(status)
        if feedback:
            state.current_iteration.review_feedback = feedback
        if ci_status:
            state.current_iteration.ci_status = ci_status

        self.save_to_pr(pr_number, state)

    @staticmethod
    def format_state_for_pr(state: AgentState) -> str:
        """Format state as hidden HTML comment for PR body.

        Args:
            state: Agent state

        Returns:
            Formatted state block
        """
        state_json = json.dumps(state.to_dict(), indent=2, ensure_ascii=False)
        return f"{STATE_MARKER_START}\n{state_json}\n{STATE_MARKER_END}"

    @staticmethod
    def extract_visible_body(body: str) -> str:
        """Extract visible body content without state block.

        Args:
            body: Full PR body

        Returns:
            Body without state block
        """
        pattern = rf"\n*{re.escape(STATE_MARKER_START)}.*?{re.escape(STATE_MARKER_END)}\n*"
        return re.sub(pattern, "", body, flags=re.DOTALL).strip()
