#!/bin/bash
# Development convenience install — for Homebrew distribution use Formula/ instead.
set -euo pipefail
PLUGIN_DIR="$(cd "$(dirname "$0")" && pwd)"
devflow-plugin register "smoke-check" "$PLUGIN_DIR/smoke_check.py"
echo "Installed smoke-check."
