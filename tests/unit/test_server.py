"""Unit tests for the webhook server."""

import pytest
import hashlib
import hmac
from unittest.mock import MagicMock, AsyncMock, patch

from fastapi.testclient import TestClient


class TestWebhookVerification:
    """Tests for webhook signature verification."""

    def test_verify_valid_signature(self):
        """Test that valid signature passes verification."""
        from patcher.server.webhooks import verify_webhook_signature

        secret = "test-secret"
        body = b'{"test": "payload"}'
        signature = "sha256=" + hmac.new(
            secret.encode(), body, hashlib.sha256
        ).hexdigest()

        with patch("patcher.server.webhooks.get_settings") as mock_settings:
            mock_settings.return_value.github_webhook_secret = secret

            request = MagicMock()
            request.headers.get.return_value = signature

            # Should not raise
            import asyncio
            result = asyncio.get_event_loop().run_until_complete(
                verify_webhook_signature(request, body)
            )
            assert result is True

    def test_verify_missing_signature(self):
        """Test that missing signature raises error."""
        from patcher.server.webhooks import verify_webhook_signature
        from fastapi import HTTPException

        with patch("patcher.server.webhooks.get_settings") as mock_settings:
            mock_settings.return_value.github_webhook_secret = "secret"

            request = MagicMock()
            request.headers.get.return_value = ""

            import asyncio
            with pytest.raises(HTTPException) as exc_info:
                asyncio.get_event_loop().run_until_complete(
                    verify_webhook_signature(request, b"body")
                )
            assert exc_info.value.status_code == 401


class TestWebhookPayloadParsing:
    """Tests for webhook payload parsing."""

    def test_parse_issue_payload(self):
        """Test parsing issue webhook payload."""
        from patcher.server.webhooks import parse_webhook_payload

        payload = {
            "action": "opened",
            "installation": {"id": 12345},
            "repository": {"full_name": "owner/repo"},
            "sender": {"login": "user"},
            "issue": {"number": 42},
        }

        result = parse_webhook_payload("issues", payload)

        assert result.event == "issues"
        assert result.action == "opened"
        assert result.installation_id == 12345
        assert result.repository == "owner/repo"
        assert result.sender == "user"

    def test_parse_pr_payload(self):
        """Test parsing pull request webhook payload."""
        from patcher.server.webhooks import parse_webhook_payload

        payload = {
            "action": "opened",
            "installation": {"id": 12345},
            "repository": {"full_name": "owner/repo"},
            "sender": {"login": "user"},
            "pull_request": {"number": 123},
        }

        result = parse_webhook_payload("pull_request", payload)

        assert result.event == "pull_request"
        assert result.action == "opened"


class TestWebhookHandlers:
    """Tests for webhook event handlers."""

    @pytest.mark.asyncio
    async def test_handle_issue_without_label(self):
        """Test that issues without ai-agent label are skipped."""
        from patcher.server.webhooks import handle_issue_event, WebhookPayload

        payload = WebhookPayload(
            event="issues",
            action="opened",
            installation_id=12345,
            repository="owner/repo",
            sender="user",
            data={
                "issue": {
                    "number": 42,
                    "labels": [],
                }
            },
        )

        result = await handle_issue_event(payload)

        assert result["status"] == "skipped"
        assert "ai-agent" in result["reason"]

    @pytest.mark.asyncio
    async def test_handle_issue_wrong_action(self):
        """Test that issues with wrong action are skipped."""
        from patcher.server.webhooks import handle_issue_event, WebhookPayload

        payload = WebhookPayload(
            event="issues",
            action="closed",
            installation_id=12345,
            repository="owner/repo",
            sender="user",
            data={
                "issue": {
                    "number": 42,
                    "labels": [{"name": "ai-agent"}],
                }
            },
        )

        result = await handle_issue_event(payload)

        assert result["status"] == "skipped"
        assert "action" in result["reason"]

    @pytest.mark.asyncio
    async def test_handle_pr_without_label(self):
        """Test that PRs without ai-generated label are skipped."""
        from patcher.server.webhooks import handle_pull_request_event, WebhookPayload

        payload = WebhookPayload(
            event="pull_request",
            action="opened",
            installation_id=12345,
            repository="owner/repo",
            sender="user",
            data={
                "pull_request": {
                    "number": 123,
                    "labels": [],
                    "head": {"ref": "feature/something"},
                }
            },
        )

        result = await handle_pull_request_event(payload)

        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_handle_patcher_pr(self):
        """Test that PRs from patcher branches are processed."""
        from patcher.server.webhooks import handle_pull_request_event, WebhookPayload

        payload = WebhookPayload(
            event="pull_request",
            action="opened",
            installation_id=12345,
            repository="owner/repo",
            sender="user",
            data={
                "pull_request": {
                    "number": 123,
                    "labels": [],
                    "head": {"ref": "patcher/issue-42-test"},
                }
            },
        )

        with patch("patcher.server.webhooks.get_github_app_auth") as mock_auth:
            mock_auth.return_value.get_installation_token = AsyncMock(return_value="token")

            with patch("patcher.server.webhooks.GitHubClient"):
                with patch("patcher.server.webhooks.get_provider"):
                    with patch("patcher.server.webhooks.ReviewAgent") as mock_agent:
                        mock_instance = MagicMock()
                        mock_instance.run = AsyncMock(return_value=MagicMock(
                            approved=True,
                            summary="Looks good",
                        ))
                        mock_agent.return_value = mock_instance

                        result = await handle_pull_request_event(payload)

        assert result["status"] == "success"


class TestGitHubAppAuth:
    """Tests for GitHub App authentication."""

    def test_generate_jwt(self):
        """Test JWT generation."""
        from patcher.server.github_app import GitHubAppAuth

        # Create mock settings
        with patch("patcher.server.github_app.get_settings") as mock_settings:
            mock_settings.return_value.github_app_id = 12345
            mock_settings.return_value.get_private_key.return_value = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyF8PbnGy0AHB7MhgISzEBQ6Y0vb6a
HCkSBwNMEP67EOjH+SR2LghLfhRwE8+DlEoT+1tgLvepjQjxSAB6aU/zJMJPLgOR
fdfT+OVv+xg7g0lxmMDXN/wBzPjK6k8xkJZ1s8L8LxKyDsnZJDRz0xdj/pFLKeYL
IfL3YBw7S/g8+GfHBnRiM7WmfFjZ2aB01g0SZzLw0mLDlAcQ6L2xzWo7+AxTnFfN
bfXEehPJaGwFDYjH8tJGXsNT8N9hO8U2bx/YfIxbPAUCJFLzk7sFVvbxZ8RLxk8b
wB7vVvDR2gj8WMHoiMpYl7Xi0qR1E8Z7pDecBwIDAQABAoIBAC7e0bDFgJM7k6eI
V2rX0jqdYjPe3x/6li/8Q2/lsFBM5mHTPAHPLS0JBER1FhLA2fLjPj6+B56/ynNz
E6C/Ey69XhREwv/jcr/dpHj4B0aFe0g2QyLwH2oQq8K3qP0nNH3Vz3p6hqlKCsqO
T8U3Zn/FE0nT8BI3fYIHMPLwANrFVrz5B7lSTBqj1DPTbgDNP4x8q3SqMPoqQ3LI
JzCC5hE6JBNB3Xp0j1xJIdjbrcZLqpNpGx9F0yAAvXqg0hGa7ZYnx6yB0TAi7F1F
HqZh8F5OoW0+/5EzRoS4Q1MRl3gkDl0BN4dfr2IZRK3LBQQ5P2fVzXS2Wgxkn0iz
PQu3uCECgYEA7e3EQFC8tQb0zPDkVBN/TJQ7sD6gmPv7f1b7HqyMf0/kLJGMQTae
dHCpxyNrHrED+wWexJ+dMrxMZe0ve3v6K+zN8q0xFmb0TDN3djD5ryJu0k+LoVcv
5LDcN0Eo0n1qLF4B7Qb1N3qHBX7nS5pM4P9FvDb7R7FcKLC97e/h8hcCgYEA4T/k
c0/aG3qJZvPT5A7pniH5L8Q1R/AJvNKjE9y/l5h8cD6mDMBYz9JdLF2a8k5QPeJG
dwLW0kP9ZPQQ8oH9hd/lMo3f1xLqzE3M7U0g/6s7f/sEmTl8Cf0f7d/y5QS2X1ql
VbKRxiK+ybBW0z6TyKYhVk+iCMGGYqKVY3HDFU0CgYEAwRh8LMb1aCFDb/6OAEDY
UOsW0Jqmd0E8BHXB0ao4HFfsx0nD8xLXWFbQsGU9iqH0zTTH0/MUMQ==
-----END RSA PRIVATE KEY-----"""

            auth = GitHubAppAuth()
            jwt_token = auth.generate_jwt()

            assert jwt_token is not None
            assert isinstance(jwt_token, str)
            assert len(jwt_token) > 0


class TestFastAPIApp:
    """Tests for FastAPI application."""

    def test_root_endpoint(self):
        """Test root endpoint returns app info."""
        with patch("patcher.server.app.get_settings") as mock_settings:
            mock_settings.return_value.host = "0.0.0.0"
            mock_settings.return_value.port = 8080
            mock_settings.return_value.debug = False
            mock_settings.return_value.github_app_id = 12345
            mock_settings.return_value.llm_provider = "claude"

            from patcher.server.app import create_app

            app = create_app()
            client = TestClient(app)

            response = client.get("/")

            assert response.status_code == 200
            assert response.json()["name"] == "Patcher"
            assert response.json()["status"] == "running"

    def test_health_endpoint(self):
        """Test health check endpoint."""
        with patch("patcher.server.app.get_settings") as mock_settings:
            mock_settings.return_value.host = "0.0.0.0"
            mock_settings.return_value.port = 8080
            mock_settings.return_value.debug = False
            mock_settings.return_value.github_app_id = 12345
            mock_settings.return_value.llm_provider = "claude"

            from patcher.server.app import create_app

            app = create_app()
            client = TestClient(app)

            response = client.get("/health")

            assert response.status_code == 200
            assert response.json()["status"] == "healthy"

    def test_ping_webhook(self):
        """Test ping webhook event."""
        with patch("patcher.server.app.get_settings") as mock_settings:
            mock_settings.return_value.host = "0.0.0.0"
            mock_settings.return_value.port = 8080
            mock_settings.return_value.debug = False
            mock_settings.return_value.github_app_id = 12345
            mock_settings.return_value.llm_provider = "claude"
            mock_settings.return_value.github_webhook_secret = ""

            from patcher.server.app import create_app

            app = create_app()
            client = TestClient(app)

            response = client.post(
                "/webhook",
                json={"zen": "test zen"},
                headers={"X-GitHub-Event": "ping"},
            )

            assert response.status_code == 200
            assert response.json()["status"] == "pong"
