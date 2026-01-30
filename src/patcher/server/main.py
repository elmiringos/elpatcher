"""Main entry point for the ElPatcher webhook server."""

import uvicorn

from patcher.server.config import get_settings


def run():
    """Run the webhook server."""
    settings = get_settings()

    uvicorn.run(
        "patcher.server.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()
