# List available recipes
default:
    just --list

# Run all test suites
test: test-sdk test-devflow test-scaffold

# Run devflow-sdk unit tests
test-sdk:
    cd devflow-sdk && uv run --extra dev pytest

# Run devflow tool tests
test-devflow:
    #!/bin/bash
    set -euo pipefail
    uv venv
    uv pip install -e "devflow-sdk/[dev]"
    uv run --no-project pytest devflow/

# Run scaffold tests (integration test enabled via DEVFLOW_SDK)
test-scaffold:
    DEVFLOW_SDK="$(pwd)/devflow-sdk" bash devflow-plugin-scaffold/tests/test_scaffold.sh
