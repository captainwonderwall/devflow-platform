#!/bin/bash
set -e

INSTALL_DIR="$(cd "$(dirname "$(realpath "$0")")" && pwd)"
SCRIPT="$INSTALL_DIR/devflow-config"

if [ ! -f "$SCRIPT" ]; then
    echo "ERROR: $SCRIPT not found. Make sure devflow-config exists in the same folder as install.sh." >&2
    exit 1
fi

source "$INSTALL_DIR/../scripts/install-tool.sh" "devflow-config" "$SCRIPT"

echo ""
echo "'devflow-config' is now available from any directory."
