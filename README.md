# ElPatcher

AI-powered code agent for automated GitHub SDLC (Software Development Life Cycle).

**Install the bot (not hosted yet):** [github.com/apps/elpatcher](https://github.com/apps/elpatcher)

## Features

- Automated issue analysis and implementation
- PR creation and code review
- CI failure analysis and fixes
- GitHub App integration

## Installation


## Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Required environment variables:
- `GITHUB_APP_ID` - GitHub App ID
- `GITHUB_PRIVATE_KEY` - GitHub App private key
- `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` - LLM provider API key

## Running

```bash
# Build Docker image
make build

# Start server
make start

# View logs
make logs

# Stop server
make stop

# Start in debug mode
make dev
```

## Exposing with ngrok

For local development, use [ngrok](https://ngrok.com/) to expose your server to GitHub webhooks:

```bash
# Install ngrok (macOS)
brew install ngrok

# Start tunnel to your server
ngrok http 8080
```

ngrok will provide a public URL like `https://abc123.ngrok-free.app`. Use this URL for:
1. GitHub App webhook URL: `https://abc123.ngrok-free.app/webhook`
2. Workflow `ELPATCHER_API_URL` (see Repository Setup below)

## Repository Setup

After installing the ElPatcher GitHub App, an onboarding PR will be created with the workflow file `.github/workflows/elpatcher.yaml`.

**Important:** Update `ELPATCHER_API_URL` in the workflow to point to your ngrok URL:

```yaml
env:
  ELPATCHER_API_URL: https://abc123.ngrok-free.app
```

Replace `abc123.ngrok-free.app` with your actual ngrok URL.
