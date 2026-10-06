#!/bin/bash
set -e

INSTALL_DIR="$(cd "$(dirname "$(realpath "$0")")" && pwd)"
SCRIPT="$INSTALL_DIR/continue-issue"

# --shell-only: skip binary install steps (used by Homebrew formula)
SHELL_ONLY=false
if [ "$1" = "--shell-only" ]; then
    SHELL_ONLY=true
fi

if ! $SHELL_ONLY; then
    if [ ! -f "$SCRIPT" ]; then
        echo "ERROR: $SCRIPT not found. Make sure continue-issue exists in the same folder as install.sh." >&2
        exit 1
    fi
    source "$INSTALL_DIR/../scripts/install-tool.sh" "continue-issue" "$SCRIPT"
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
SENTINEL="# >>> continue-issue shell integration >>>"

if [ -z "$RC_FILE" ]; then
    echo ""
    echo "NOTE: Could not detect shell rc file. Add this function manually to your shell config:"
    echo ""
    echo "  # >>> continue-issue shell integration >>>"
    echo "  continue-issue() {"
    echo "      command continue-issue \"\$@\" || return"
    echo "      local _rc=0"
    echo "      if [ -f ~/.continue-issue-branch ] && [ -f ~/.continue-issue-worktree-path ]; then"
    echo "          wt -C \"\$(cat ~/.continue-issue-worktree-path)\" switch \"\$(cat ~/.continue-issue-branch)\" || _rc=\$?"
    echo "      fi"
    echo "      rm -f ~/.continue-issue-branch ~/.continue-issue-worktree-path"
    echo "      return \$_rc"
    echo "  }"
    echo "  # <<< continue-issue shell integration <<<"
elif grep -qF "$SENTINEL" "$RC_FILE" 2>/dev/null; then
    if grep -qF '~/.continue-issue-worktree-path' "$RC_FILE" 2>/dev/null \
        && grep -qF 'wt -C' "$RC_FILE" 2>/dev/null; then
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
    "# >>> continue-issue shell integration >>>\n"
    "continue-issue() {\n"
    "    command continue-issue \"$@\" || return\n"
    "    local _rc=0\n"
    "    if [ -f ~/.continue-issue-branch ] && [ -f ~/.continue-issue-worktree-path ]; then\n"
    "        wt -C \"$(cat ~/.continue-issue-worktree-path)\" switch \"$(cat ~/.continue-issue-branch)\" || _rc=$?\n"
    "    fi\n"
    "    rm -f ~/.continue-issue-branch ~/.continue-issue-worktree-path\n"
    "    return $_rc\n"
    "}\n"
    "# <<< continue-issue shell integration <<<"
)

updated = re.sub(
    r"# >>> continue-issue shell integration >>>.*?# <<< continue-issue shell integration <<<",
    new_block,
    content,
    flags=re.DOTALL,
)

with open(rc_file, "w") as f:
    f.write(updated)
PYEOF
        echo "Updated continue-issue shell function in $RC_FILE."
        echo "Restart your shell or run: source $RC_FILE"
    fi
else
    cat >> "$RC_FILE" << 'SHELL_FUNC'

# >>> continue-issue shell integration >>>
continue-issue() {
    command continue-issue "$@" || return
    local _rc=0
    if [ -f ~/.continue-issue-branch ] && [ -f ~/.continue-issue-worktree-path ]; then
        wt -C "$(cat ~/.continue-issue-worktree-path)" switch "$(cat ~/.continue-issue-branch)" || _rc=$?
    fi
    rm -f ~/.continue-issue-branch ~/.continue-issue-worktree-path
    return $_rc
}
# <<< continue-issue shell integration <<<
SHELL_FUNC
    echo "Added continue-issue shell function to $RC_FILE."
    echo "Restart your shell or run: source $RC_FILE"
fi

if ! $SHELL_ONLY; then
    echo ""
    echo "'continue-issue' is now available from any directory."
    echo ""
    echo "Prerequisites:"
    echo "  brew install worktrunk"
    echo "  wt config shell install"
fi
