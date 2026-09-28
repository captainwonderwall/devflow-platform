#!/bin/bash
set -e

INSTALL_DIR="$(cd "$(dirname "$(realpath "$0")")" && pwd)"
SCRIPT="$INSTALL_DIR/diagram"

if [ ! -f "$SCRIPT" ]; then
    echo "ERROR: $SCRIPT not found. Make sure diagram exists in the same folder as install.sh." >&2
    exit 1
fi

source "$INSTALL_DIR/../scripts/install-tool.sh" "diagram" "$SCRIPT"

echo ""
echo "'diagram' is now available from any directory."
echo ""
echo "Prerequisites:"
echo "  docker (https://docs.docker.com/get-docker/)"
