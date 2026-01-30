# ElPatcher

AI-powered code agent for automated GitHub SDLC (Software Development Life Cycle).

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

## Repository Setup

After installing the ElPatcher GitHub App, an onboarding PR will be created with the workflow file `.github/workflows/elpatcher.yaml`.

**Important:** Update `ELPATCHER_API_URL` in the workflow to point to your server:

```yaml
env:
  ELPATCHER_API_URL: https://your-server.example.com
```

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


