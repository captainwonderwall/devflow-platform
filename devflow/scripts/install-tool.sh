#!/bin/bash
# Sourced by each tool's install.sh for shared binary-install boilerplate.
# Usage: source scripts/install-tool.sh <tool-name> <script-absolute-path>
# After sourcing, RC_FILE is set (may be empty if shell is unrecognized).

_TOOL_NAME="$1"
_SCRIPT_PATH="$2"

case "$(basename "$SHELL")" in
    zsh)  RC_FILE="$HOME/.zshrc" ;;
    bash) RC_FILE="$HOME/.bashrc" ;;
    *)    RC_FILE="" ;;
esac

BIN_DIR="$HOME/bin"
mkdir -p "$BIN_DIR"

if ! echo ":$PATH:" | grep -Fq ":$BIN_DIR:"; then
    if [ -n "$RC_FILE" ]; then
        echo "export PATH=\"\$HOME/bin:\$PATH\"" >> "$RC_FILE"
        echo "NOTE: Added ~/bin to PATH in $RC_FILE."
        echo "Restart your shell or run: source $RC_FILE"
    else
        echo "NOTE: $BIN_DIR is not on your PATH."
        echo "Add it to your shell config manually:"
        echo "  export PATH=\"\$HOME/bin:\$PATH\""
    fi
    echo ""
fi

_LINK="$BIN_DIR/$_TOOL_NAME"

if [ -L "$_LINK" ]; then
    _CURRENT="$(readlink "$_LINK")"
    if [ "$_CURRENT" = "$_SCRIPT_PATH" ]; then
        echo "Symlink already installed: $_LINK -> $_SCRIPT_PATH"
    else
        echo "ERROR: $_LINK already exists and points elsewhere: $_CURRENT" >&2
        echo "Remove it manually to reinstall: rm $_LINK" >&2
        exit 1
    fi
elif [ -e "$_LINK" ]; then
    echo "ERROR: $_LINK already exists as a regular file." >&2
    echo "Remove it manually to install: rm $_LINK" >&2
    exit 1
else
    ln -s "$_SCRIPT_PATH" "$_LINK"
    echo "Installed: $_LINK -> $_SCRIPT_PATH"
fi
