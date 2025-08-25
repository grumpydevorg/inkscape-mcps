# Modern task runner for Inkscape MCP Server
# Install just: https://github.com/casey/just

# Show available commands
default:
    @just --list

# Install package with dev dependencies
install:
    uv sync --dev

# Run tests
test:
    uv run pytest

# Run linting
lint:
    uv run ruff check src/

# Format code
format:
    uv run black src/
    uv run ruff check --fix src/

# Run type checking
type-check:
    uv run ty check src/

# Run all checks
check: lint type-check test

# Build distribution packages
build:
    uv build

# Clean build artifacts  
clean:
    rm -rf build/
    rm -rf dist/
    rm -rf *.egg-info/
    find . -type d -name __pycache__ -exec rm -rf {} +
    find . -type f -name "*.pyc" -delete

# Development setup
setup: install
    @echo "Development environment ready!"
    @echo "Run 'just --list' to see available commands"

# Test individual servers
test-cli:
    uv run python -m inkscape_mcp.cli_server

test-dom:
    uv run python -m inkscape_mcp.dom_server

test-combined:
    uv run python -m inkscape_mcp.combined

# Install the package locally for testing
install-local:
    uv pip install -e .