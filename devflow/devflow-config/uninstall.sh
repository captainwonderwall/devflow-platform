#!/bin/bash
set -e

INSTALL_DIR="$(cd "$(dirname "$(realpath "$0")")" && pwd)"
SCRIPT="$INSTALL_DIR/devflow-config"

find_link() {
    IFS=: read -ra DIRS <<< "$PATH"
    for dir in "${DIRS[@]}"; do
        candidate="$dir/devflow-config"
        if [ -L "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

LINK="$(find_link)" || {
    echo "devflow-config is not installed (no symlink named 'devflow-config' found on PATH)."
    exit 0
}

CURRENT_TARGET="$(readlink "$LINK")"
if [ "$CURRENT_TARGET" != "$SCRIPT" ]; then
    echo "ERROR: $LINK points to $CURRENT_TARGET, not $SCRIPT." >&2
    echo "This symlink was not created by this install.sh. Remove it manually if intended: rm $LINK" >&2
    exit 1
fi

rm "$LINK"
echo "Uninstalled: removed $LINK"
