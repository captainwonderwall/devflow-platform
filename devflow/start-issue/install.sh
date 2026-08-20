#!/bin/bash
set -e

INSTALL_DIR="$(cd "$(dirname "$(realpath "$0")")" && pwd)"
SCRIPT="$INSTALL_DIR/start-issue"

# --shell-only: skip binary install steps (used by Homebrew formula)
SHELL_ONLY=false
if [ "$1" = "--shell-only" ]; then
    SHELL_ONLY=true
fi

if ! $SHELL_ONLY; then
    if [ ! -f "$SCRIPT" ]; then
        echo "ERROR: $SCRIPT not found. Make sure start-issue exists in the same folder as install.sh." >&2
        exit 1
    fi
    source "$INSTALL_DIR/../scripts/install-tool.sh" "start-issue" "$SCRIPT"
fi

# Determine RC_FILE when running --shell-only (install-tool.sh normally sets it)
if $SHELL_ONLY; then
    case "$(basename "$SHELL")" in
        zsh)  RC_FILE="$HOME/.zshrc" ;;
        bash) RC_FILE="$HOME/.bashrc" ;;
        *)    RC_FILE="" ;;
    esac
fi

# ── Inject shell function for worktree switching ─────────────────────────────
SENTINEL="# >>> start-issue shell integration >>>"

if [ -z "$RC_FILE" ]; then
    echo ""
    echo "NOTE: Could not detect shell rc file. Add this function manually to your shell config:"
    echo ""
    echo "  # >>> start-issue shell integration >>>"
    echo "  start-issue() {"
    echo "      command start-issue \"\$@\" || return"
    echo "      local _rc=0"
    echo "      if [ -f ~/.start-issue-branch ]; then"
    echo "          wt switch \"\$(cat ~/.start-issue-branch)\" || _rc=\$?"
    echo "      fi"
    echo "      rm -f ~/.start-issue-branch"
    echo "      return \$_rc"
    echo "  }"
    echo "  # <<< start-issue shell integration <<<"
elif grep -qF "$SENTINEL" "$RC_FILE" 2>/dev/null; then
    if grep -qF '~/.start-issue-branch' "$RC_FILE" 2>/dev/null; then
        echo "Shell function already present in $RC_FILE."
    else
        if ! command -v python3 &>/dev/null; then
            echo "ERROR: python3 is required to upgrade the stale shell integration but was not found." >&2
            exit 1
        fi
        python3 - "$RC_FILE" << 'PYEOF'
import sys, re

rc_file = sys.argv[1]
with open(rc_file) as f:
    content = f.read()

new_block = (
    "# >>> start-issue shell integration >>>\n"
    "start-issue() {\n"
    "    command start-issue \"$@\" || return\n"
    "    local _rc=0\n"
    "    if [ -f ~/.start-issue-branch ]; then\n"
    "        wt switch \"$(cat ~/.start-issue-branch)\" || _rc=$?\n"
    "    fi\n"
    "    rm -f ~/.start-issue-branch\n"
    "    return $_rc\n"
    "}\n"
    "# <<< start-issue shell integration <<<"
)

updated = re.sub(
    r"# >>> start-issue shell integration >>>.*?# <<< start-issue shell integration <<<",
    new_block,
    content,
    flags=re.DOTALL,
)

with open(rc_file, "w") as f:
    f.write(updated)
PYEOF
        echo "Updated start-issue shell function in $RC_FILE."
        echo "Restart your shell or run: source $RC_FILE"
    fi
else
    cat >> "$RC_FILE" << 'SHELL_FUNC'

# >>> start-issue shell integration >>>
start-issue() {
    command start-issue "$@" || return
    local _rc=0
    if [ -f ~/.start-issue-branch ]; then
        wt switch "$(cat ~/.start-issue-branch)" || _rc=$?
    fi
    rm -f ~/.start-issue-branch
    return $_rc
}
# <<< start-issue shell integration <<<
SHELL_FUNC
    echo "Added start-issue shell function to $RC_FILE."
    echo "Restart your shell or run: source $RC_FILE"
fi

if ! $SHELL_ONLY; then
    echo ""
    echo "'start-issue' is now available from any directory."
    echo ""
    echo "Prerequisites:"
    echo "  brew install worktrunk"
    echo "  wt config shell install"
    echo "  brew install gh               # for GitHub issues"
    echo "  brew tap atlassian/homebrew-acli && brew install acli  # for JIRA issues"
    echo "  claude CLI: https://claude.ai/code"
fi
