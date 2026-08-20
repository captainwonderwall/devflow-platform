#!/bin/bash
set -e

INSTALL_DIR="$(cd "$(dirname "$(realpath "$0")")" && pwd)"
SCRIPT="$INSTALL_DIR/finish-issue"

# --shell-only: skip binary install steps (used by Homebrew formula)
SHELL_ONLY=false
if [ "$1" = "--shell-only" ]; then
    SHELL_ONLY=true
fi

if ! $SHELL_ONLY; then
    if [ ! -f "$SCRIPT" ]; then
        echo "ERROR: $SCRIPT not found. Make sure finish-issue exists in the same folder as install.sh." >&2
        exit 1
    fi
    source "$INSTALL_DIR/../scripts/install-tool.sh" "finish-issue" "$SCRIPT"
fi

# Determine RC_FILE when running --shell-only (install-tool.sh normally sets it)
if $SHELL_ONLY; then
    case "$(basename "$SHELL")" in
        zsh)  RC_FILE="$HOME/.zshrc" ;;
        bash) RC_FILE="$HOME/.bashrc" ;;
        *)    RC_FILE="" ;;
    esac
fi

# ── Inject shell function for worktree switching ────────────────────────────
SENTINEL="# >>> finish-issue shell integration >>>"

if [ -z "$RC_FILE" ]; then
    echo ""
    echo "NOTE: Could not detect shell rc file. Add this function manually to your shell config:"
    echo ""
    echo "  # >>> finish-issue shell integration >>>"
    echo "  finish-issue() {"
    echo "      command finish-issue --prepare \"\$@\" || return"
    echo "      local _rc=0"
    echo "      local _switch_to _remove _force"
    echo "      _switch_to=\"\$(cat ~/.finish-issue-branch 2>/dev/null || true)\""
    echo "      _remove=\"\$(cat ~/.finish-issue-remove 2>/dev/null || true)\""
    echo "      if [ -n \"\$_switch_to\" ]; then"
    echo "          wt switch \"\$_switch_to\" || return \$?"
    echo "          rm -f ~/.finish-issue-branch"
    echo "      fi"
    echo "      if [ -n \"\$_remove\" ]; then"
    echo "          _force=\"\""
    echo "          if [ -f ~/.finish-issue-force ]; then"
    echo "              _force=\"--force\""
    echo "          fi"
    echo "          wt remove \$_force \"\$_remove\" || _rc=\$?"
    echo "          rm -f ~/.finish-issue-remove ~/.finish-issue-force"
    echo "      fi"
    echo "      return \$_rc"
    echo "  }"
    echo "  # <<< finish-issue shell integration <<<"
elif grep -qF "$SENTINEL" "$RC_FILE" 2>/dev/null; then
    if grep -qF 'command finish-issue --prepare' "$RC_FILE" 2>/dev/null \
       && grep -qF '.finish-issue-force' "$RC_FILE" 2>/dev/null; then
        echo "Shell function already present in $RC_FILE."
        echo ""
        echo "NOTE: If your current terminal session was started before this"
        echo "function was added (or before a previous version of it was fixed),"
        echo "it is still running the old definition in memory. Restart your shell"
        echo "or run: source \"$RC_FILE\""
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
    "# >>> finish-issue shell integration >>>\n"
    "finish-issue() {\n"
    "    command finish-issue --prepare \"$@\" || return\n"
    "    local _rc=0\n"
    "    local _switch_to _remove _worktree_path\n"
    "    _switch_to=\"$(cat ~/.finish-issue-branch 2>/dev/null || true)\"\n"
    "    _remove=\"$(cat ~/.finish-issue-remove 2>/dev/null || true)\"\n"
    "    _worktree_path=\"$(cat ~/.finish-issue-worktree-path 2>/dev/null || true)\"\n"
    "    if [ -n \"$_worktree_path\" ] && [ -f ~/.finish-issue-force ]; then\n"
    "        git -C \"$_worktree_path\" reset --hard HEAD 2>/dev/null || true\n"
    "        git -C \"$_worktree_path\" clean -fd 2>/dev/null || true\n"
    "    fi\n"
    "    if [ -n \"$_switch_to\" ]; then\n"
    "        wt switch \"$_switch_to\" || return $?\n"
    "        rm -f ~/.finish-issue-branch\n"
    "    fi\n"
    "    if [ -n \"$_remove\" ]; then\n"
    "        wt remove \"$_remove\" || _rc=$?\n"
    "        rm -f ~/.finish-issue-remove ~/.finish-issue-force ~/.finish-issue-worktree-path\n"
    "    fi\n"
    "    return $_rc\n"
    "}\n"
    "# <<< finish-issue shell integration <<<"
)

updated = re.sub(
    r"# >>> finish-issue shell integration >>>.*?# <<< finish-issue shell integration <<<",
    new_block,
    content,
    flags=re.DOTALL,
)

with open(rc_file, "w") as f:
    f.write(updated)
PYEOF
        echo "Updated finish-issue shell function in $RC_FILE."
        echo "Restart your shell or run: source $RC_FILE"
    fi
else
    cat >> "$RC_FILE" << 'SHELL_FUNC'

# >>> finish-issue shell integration >>>
finish-issue() {
    command finish-issue --prepare "$@" || return
    local _rc=0
    local _switch_to _remove _worktree_path
    _switch_to="$(cat ~/.finish-issue-branch 2>/dev/null || true)"
    _remove="$(cat ~/.finish-issue-remove 2>/dev/null || true)"
    _worktree_path="$(cat ~/.finish-issue-worktree-path 2>/dev/null || true)"
    if [ -n "$_worktree_path" ] && [ -f ~/.finish-issue-force ]; then
        git -C "$_worktree_path" reset --hard HEAD 2>/dev/null || true
        git -C "$_worktree_path" clean -fd 2>/dev/null || true
    fi
    if [ -n "$_switch_to" ]; then
        wt switch "$_switch_to" || return $?
        rm -f ~/.finish-issue-branch
    fi
    if [ -n "$_remove" ]; then
        wt remove "$_remove" || _rc=$?
        rm -f ~/.finish-issue-remove ~/.finish-issue-force ~/.finish-issue-worktree-path
    fi
    return $_rc
}
# <<< finish-issue shell integration <<<
SHELL_FUNC
    echo "Added finish-issue shell function to $RC_FILE."
    echo "Restart your shell or run: source $RC_FILE"
fi

if ! $SHELL_ONLY; then
    echo ""
    echo "'finish-issue' is now available from any directory."
    echo ""
    echo "Prerequisites:"
    echo "  brew install worktrunk"
    echo "  wt config shell install"
    echo "  brew install gh               # for GitHub issues"
    echo "  brew tap atlassian/homebrew-acli && brew install acli  # for JIRA issues"
fi
