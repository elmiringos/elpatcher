.PHONY: build start stop logs restart dev test lint format check clean help

# =============================================================================
# Server
# =============================================================================

# Build Docker image
build:
	docker-compose build

# Start server
start:
	docker-compose up -d

# Stop server
stop:
	docker-compose down

# View logs
logs:
	docker-compose logs -f

# Restart server
restart: stop start

# Start in development mode (with DEBUG)
dev:
	DEBUG=true LOG_LEVEL=DEBUG docker-compose up

# =============================================================================
# Development
# =============================================================================

# Install with development dependencies
install-dev:
	pip install -e ".[dev]"

# Run tests
test:
	pytest tests/ -v --cov=src/patcher --cov-report=term

# Run linting
lint:
	ruff check src/ tests/

# Format code
format:
	ruff format src/ tests/
	ruff check --fix src/ tests/

# Run type checking
type-check:
	mypy src/

# Run all checks
check: lint type-check test

# Clean build artifacts
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +

# =============================================================================
# Help
# =============================================================================

help:
	@echo "Patcher - AI Code Agent for GitHub"
	@echo ""
	@echo "Server:"
	@echo "  make build     - Build Docker image"
	@echo "  make start     - Start server"
	@echo "  make stop      - Stop server"
	@echo "  make logs      - View logs"
	@echo "  make restart   - Restart server"
	@echo "  make dev       - Start in debug mode"
	@echo ""
	@echo "Development:"
	@echo "  make install-dev  - Install dev dependencies"
	@echo "  make test         - Run tests"
	@echo "  make lint         - Run linter"
	@echo "  make format       - Format code"
	@echo "  make check        - Run all checks"
	@echo "  make clean        - Clean artifacts"
	@echo ""
	@echo "Environment variables:"
	@echo "  GITHUB_APP_ID              - GitHub App ID"
	@echo "  GITHUB_APP_PRIVATE_KEY_PATH - Path to private key"
	@echo "  GITHUB_WEBHOOK_SECRET      - Webhook secret"
	@echo "  LLM_PROVIDER               - claude or openai"
	@echo "  ANTHROPIC_API_KEY          - Anthropic API key"
