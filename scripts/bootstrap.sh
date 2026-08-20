#!/usr/bin/env bash
# One-time dev setup: installs uv (if needed) and seeds the vendor wheel.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ── Install uv ────────────────────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
    echo "==> Installing uv via Homebrew..."
    brew install uv
else
    echo "==> uv already installed ($(uv --version))"
fi

# ── Build SDK wheel and seed vendor ──────────────────────────────────────────
echo "==> Building devflow-sdk wheel..."
(cd "$REPO_ROOT/devflow-sdk" && uv build --wheel)

WHEEL=$(ls "$REPO_ROOT/devflow-sdk/dist/devflow_sdk-"*.whl | sort -V | tail -1)
[[ -f "$WHEEL" ]] || { echo "ERROR: wheel not found in devflow-sdk/dist/" >&2; exit 1; }

mkdir -p "$REPO_ROOT/devflow/vendor"
rm -f "$REPO_ROOT/devflow/vendor"/devflow_sdk-*.whl
cp "$WHEEL" "$REPO_ROOT/devflow/vendor/"

echo ""
echo "==> Bootstrap complete."
echo "    Vendor wheel: devflow/vendor/$(basename "$WHEEL")"
echo ""
echo "    To run SDK tests:    uv run --no-project pytest devflow-sdk/"
echo "    To run devflow tests: uv run --no-project pytest devflow/"
