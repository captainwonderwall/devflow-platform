#!/bin/bash
set -e

INSTALL_DIR="$(cd "$(dirname "$(realpath "$0")")" && pwd)"
SCRIPT="$INSTALL_DIR/draft-pr"

if [ ! -f "$SCRIPT" ]; then
    echo "ERROR: $SCRIPT not found. Make sure draft-pr exists in the same folder as install.sh." >&2
    exit 1
fi

source "$INSTALL_DIR/../scripts/install-tool.sh" "draft-pr" "$SCRIPT"

echo ""
echo "'draft-pr' is now available from any directory."
echo ""
echo "Prerequisites:"
echo "  brew install gh"
echo "  claude CLI: https://claude.ai/code"
