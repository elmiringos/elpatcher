"""GitHub App authentication and client management."""

import time
from dataclasses import dataclass
from functools import lru_cache

import jwt
import httpx
from github import Github, GithubIntegration

from patcher.server.config import Settings, get_settings


@dataclass
class InstallationAuth:
    """Authentication for a GitHub App installation."""

    installation_id: int
    token: str
    expires_at: float


class GitHubAppAuth:
    """GitHub App authentication manager."""

    def __init__(self, settings: Settings | None = None):
        """Initialize GitHub App authentication.

        Args:
            settings: Server settings (uses default if not provided)
        """
        self.settings = settings or get_settings()
        self._private_key = self.settings.get_private_key()
        self._app_id = self.settings.github_app_id
        self._installation_tokens: dict[int, InstallationAuth] = {}

    def generate_jwt(self, expiration_seconds: int = 600) -> str:
        """Generate a JWT for GitHub App authentication.

        Args:
            expiration_seconds: JWT expiration time in seconds

        Returns:
            JWT token string
        """
        now = int(time.time())
        payload = {
            "iat": now - 60,  # Issued at (60s in the past for clock drift)
            "exp": now + expiration_seconds,
            "iss": self._app_id,
        }
        return jwt.encode(payload, self._private_key, algorithm="RS256")

    async def get_installation_token(self, installation_id: int) -> str:
        """Get an installation access token.

        Args:
            installation_id: GitHub App installation ID

        Returns:
            Installation access token
        """
        # Check if we have a valid cached token
        cached = self._installation_tokens.get(installation_id)
        if cached and cached.expires_at > time.time() + 300:  # 5 min buffer
            return cached.token

        # Request a new token
        jwt_token = self.generate_jwt()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.github.com/app/installations/{installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {jwt_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            response.raise_for_status()
            data = response.json()

        # Parse expiration
        expires_at = time.time() + 3600  # Default 1 hour
        if "expires_at" in data:
            # Parse ISO format datetime
            from datetime import datetime
            exp_dt = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
            expires_at = exp_dt.timestamp()

        # Cache the token
        auth = InstallationAuth(
            installation_id=installation_id,
            token=data["token"],
            expires_at=expires_at,
        )
        self._installation_tokens[installation_id] = auth

        return auth.token

    def get_installation_client(self, installation_id: int, token: str) -> Github:
        """Get a PyGithub client for an installation.

        Args:
            installation_id: GitHub App installation ID
            token: Installation access token

        Returns:
            Authenticated PyGithub client
        """
        return Github(token)

    async def get_client_for_installation(self, installation_id: int) -> Github:
        """Get an authenticated client for an installation.

        Args:
            installation_id: GitHub App installation ID

        Returns:
            Authenticated PyGithub client
        """
        token = await self.get_installation_token(installation_id)
        return self.get_installation_client(installation_id, token)

    async def get_installation_for_repo(self, repo_full_name: str) -> int | None:
        """Get installation ID for a repository.

        Args:
            repo_full_name: Repository full name (owner/repo)

        Returns:
            Installation ID or None if not found
        """
        jwt_token = self.generate_jwt()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.github.com/repos/{repo_full_name}/installation",
                headers={
                    "Authorization": f"Bearer {jwt_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()

        return data.get("id")

    async def get_token_for_repo(self, repo_full_name: str) -> str | None:
        """Get installation token for a repository.

        Args:
            repo_full_name: Repository full name (owner/repo)

        Returns:
            Installation access token or None if app not installed
        """
        installation_id = await self.get_installation_for_repo(repo_full_name)
        if not installation_id:
            return None
        return await self.get_installation_token(installation_id)

    def get_app_info(self) -> dict:
        """Get information about the GitHub App.

        Returns:
            App information dictionary
        """
        jwt_token = self.generate_jwt()
        integration = GithubIntegration(
            integration_id=self._app_id,
            private_key=self._private_key,
        )
        return {
            "app_id": self._app_id,
            "name": "Patcher",
        }


@lru_cache
def get_github_app_auth() -> GitHubAppAuth:
    """Get cached GitHub App auth instance."""
    return GitHubAppAuth()
