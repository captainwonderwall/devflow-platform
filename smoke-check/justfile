# List available recipes
default:
    just --list

# Install dev dependencies into a local venv
dev:
    uv sync --extra dev

# Run tests
test:
    uv run --extra dev pytest tests/

# Build wheel
build:
    uv build --wheel

# Refresh vendor/ from declared runtime deps in pyproject.toml
vendor:
    bash scripts/update-vendor.sh
