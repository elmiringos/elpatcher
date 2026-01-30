# Patcher

AI-powered code agent for automated GitHub SDLC (Software Development Life Cycle).

## Features

- Automated issue analysis and implementation
- PR creation and code review
- CI failure analysis and fixes
- GitHub App integration

## Installation

```bash
poetry install
```

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Required environment variables:
- `GITHUB_APP_ID` - GitHub App ID
- `GITHUB_PRIVATE_KEY` - GitHub App private key
- `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` - LLM provider API key

## Usage

Start the webhook server:

```bash
patcher-server
```

## Development

```bash
poetry install --with dev
pytest
```

## License

MIT
