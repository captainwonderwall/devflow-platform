#!/bin/bash
# Run once after installing devflow via Homebrew to set up shell integrations
# for tools that need to switch your working directory.
set -e

LIBEXEC="$(brew --prefix)/opt/devflow/libexec"

[ -d "$LIBEXEC" ] || { echo "ERROR: devflow not installed. Run: brew install devflow"; exit 1; }

bash "$LIBEXEC/start-issue/install.sh" --shell-only
bash "$LIBEXEC/finish-issue/install.sh" --shell-only

echo ""
echo "Done. Reload your shell to activate:"
echo "  source ~/.zshrc   # or ~/.bashrc"
