"""FastAPI application for GitHub App webhook handling."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

from patcher.server.config import get_settings
from patcher.server.webhooks import verify_webhook_signature, handle_webhook
from patcher.server.github_app import get_github_app_auth
from patcher.server.api import router as api_router


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    settings = get_settings()
    logger.info(f"Starting Patcher webhook server on {settings.host}:{settings.port}")
    logger.info(f"GitHub App ID: {settings.github_app_id}")
    logger.info(f"LLM Provider: {settings.llm_provider}")
    yield
    logger.info("Shutting down Patcher webhook server")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI app
    """
    settings = get_settings()

    app = FastAPI(
        title="Patcher",
        description="GitHub App for automated code generation and review",
        version="0.1.0",
        lifespan=lifespan,
        debug=settings.debug,
    )

    @app.get("/")
    async def root():
        """Root endpoint with app info."""
        return {
            "name": "Patcher",
            "version": "0.1.0",
            "description": "GitHub App for automated SDLC",
            "status": "running",
        }

    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return {"status": "healthy"}

    @app.post("/webhook")
    async def webhook(request: Request, background_tasks: BackgroundTasks):
        """GitHub webhook endpoint.

        Receives webhook events from GitHub and processes them.
        """
        # Get raw body for signature verification
        body = await request.body()

        # Verify webhook signature
        await verify_webhook_signature(request, body)

        # Parse payload
        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

        # Get event type
        event_type = request.headers.get("X-GitHub-Event", "")
        if not event_type:
            raise HTTPException(status_code=400, detail="Missing X-GitHub-Event header")

        # Handle ping event
        if event_type == "ping":
            return {"status": "pong", "zen": payload.get("zen", "")}

        # Process webhook in background for long-running tasks
        background_tasks.add_task(process_webhook_async, event_type, payload)

        return {
            "status": "accepted",
            "event": event_type,
            "action": payload.get("action", ""),
        }

    @app.get("/app")
    async def app_info():
        """Get GitHub App information."""
        try:
            app_auth = get_github_app_auth()
            info = app_auth.get_app_info()
            return info
        except Exception as e:
            return {"error": str(e)}

    @app.get("/installations")
    async def list_installations():
        """List GitHub App installations.

        Note: This requires app-level authentication.
        """
        return {"message": "Not implemented - use GitHub API directly"}

    # Include API router for synchronous operations
    app.include_router(api_router)

    return app


async def process_webhook_async(event_type: str, payload: dict):
    """Process webhook asynchronously.

    Args:
        event_type: GitHub event type
        payload: Webhook payload
    """
    try:
        result = await handle_webhook(event_type, payload)
        logger.info(f"Webhook processed: {result}")
    except Exception as e:
        logger.exception(f"Error processing webhook: {e}")


# Create default app instance
app = create_app()
