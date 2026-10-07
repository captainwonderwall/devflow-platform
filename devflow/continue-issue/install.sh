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
else
    touch "$RC_FILE"
    if ! command -v python3 &>/dev/null; then
        echo "ERROR: python3 is required to install the shell integration but was not found." >&2
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

pattern = re.compile(
    r"# >>> continue-issue shell integration >>>.*?# <<< continue-issue shell integration <<<",
    flags=re.DOTALL,
)
matches = list(pattern.finditer(content))
if matches:
    replacement_index = 0

    def replace_block(_match):
        global replacement_index
        replacement_index += 1
        return new_block if replacement_index == 1 else ""

    updated = pattern.sub(replace_block, content)
    print(f"Updated continue-issue shell function in {rc_file}.")
else:
    separator = "" if not content else ("" if content.endswith("\n\n") else "\n" if content.endswith("\n") else "\n\n")
    updated = content + separator + new_block + "\n"
    print(f"Added continue-issue shell function to {rc_file}.")

with open(rc_file, "w") as f:
    f.write(updated)
PYEOF
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
