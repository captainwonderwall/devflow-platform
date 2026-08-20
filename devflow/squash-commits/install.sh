#!/bin/bash
set -e

INSTALL_DIR="$(cd "$(dirname "$(realpath "$0")")" && pwd)"
SCRIPT="$INSTALL_DIR/squash-commits"

if [ ! -f "$SCRIPT" ]; then
    echo "ERROR: $SCRIPT not found. Make sure squash-commits exists in the same folder as install.sh." >&2
    exit 1
fi

source "$INSTALL_DIR/../scripts/install-tool.sh" "squash-commits" "$SCRIPT"

echo ""
echo "'squash-commits' is now available from any directory."
echo ""
echo "Prerequisites:"
echo "  brew install gh"
echo "  claude CLI: https://claude.ai/code"
