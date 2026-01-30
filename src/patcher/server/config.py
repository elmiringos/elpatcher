"""Configuration for the webhook server."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server configuration settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = False

    # GitHub App settings
    github_app_id: int
    github_app_private_key: str = ""
    github_app_private_key_path: str = ""
    github_webhook_secret: str = ""

    # LLM settings
    llm_provider: str = "claude"
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # Agent settings
    max_iterations: int = 5
    auto_merge: bool = False

    # Logging
    log_level: str = "INFO"

    def get_private_key(self) -> str:
        """Get the GitHub App private key."""
        if self.github_app_private_key:
            return self.github_app_private_key

        if self.github_app_private_key_path:
            key_path = Path(self.github_app_private_key_path)
            if key_path.exists():
                return key_path.read_text()

        raise ValueError(
            "GitHub App private key not configured. "
            "Set GITHUB_APP_PRIVATE_KEY or GITHUB_APP_PRIVATE_KEY_PATH"
        )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()  # type: ignore[call-arg]
