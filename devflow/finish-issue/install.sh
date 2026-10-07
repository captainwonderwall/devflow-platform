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
    echo "      local _switch_to _remove _worktree_path"
    echo "      _switch_to=\"\$(cat ~/.finish-issue-branch 2>/dev/null || true)\""
    echo "      _remove=\"\$(cat ~/.finish-issue-remove 2>/dev/null || true)\""
    echo "      _worktree_path=\"\$(cat ~/.finish-issue-worktree-path 2>/dev/null || true)\""
    echo "      if [ -n \"\$_worktree_path\" ] && [ -f ~/.finish-issue-force ]; then"
    echo "          git -C \"\$_worktree_path\" reset --hard HEAD 2>/dev/null || true"
    echo "          git -C \"\$_worktree_path\" clean -fd 2>/dev/null || true"
    echo "      fi"
    echo "      if [ -n \"\$_switch_to\" ]; then"
    echo "          wt -C \"\$_worktree_path\" switch \"\$_switch_to\" || return \$?"
    echo "          rm -f ~/.finish-issue-branch"
    echo "      fi"
    echo "      if [ -n \"\$_remove\" ]; then"
    echo "          if [ -f ~/.finish-issue-force-delete ]; then"
    echo "              wt remove --force \"\$_remove\" || _rc=\$?"
    echo "          else"
    echo "              wt remove \"\$_remove\" || _rc=\$?"
    echo "          fi"
    echo "          if [ -n \"\$_worktree_path\" ] && [ -d \"\$_worktree_path\" ]; then"
    echo "              rm -rf \"\$_worktree_path\""
    echo "          fi"
    echo "          rm -f ~/.finish-issue-remove ~/.finish-issue-force ~/.finish-issue-worktree-path ~/.finish-issue-force-delete"
    echo "      fi"
    echo "      return \$_rc"
    echo "  }"
    echo "  # <<< finish-issue shell integration <<<"
else
    touch "$RC_FILE"
    if ! command -v python3 &>/dev/null; then
        echo "ERROR: python3 is required to install the shell integration but was not found." >&2
        exit 1
    fi
    python3 - "$RC_FILE" << 'PYEOF'
import re
import sys

rc_file = sys.argv[1]
with open(rc_file) as file:
    content = file.read()

start = "# >>> finish-issue shell integration >>>"
end = "# <<< finish-issue shell integration <<<"
new_block = '''# >>> finish-issue shell integration >>>
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
        wt -C "$_worktree_path" switch "$_switch_to" || return $?
        rm -f ~/.finish-issue-branch
    fi
    if [ -n "$_remove" ]; then
        if [ -f ~/.finish-issue-force-delete ]; then
            wt remove --force "$_remove" || _rc=$?
        else
            wt remove "$_remove" || _rc=$?
        fi
        if [ -n "$_worktree_path" ] && [ -d "$_worktree_path" ]; then
            rm -rf "$_worktree_path"
        fi
        rm -f ~/.finish-issue-remove ~/.finish-issue-force ~/.finish-issue-worktree-path ~/.finish-issue-force-delete
    fi
    return $_rc
}
# <<< finish-issue shell integration <<<'''
pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
matches = list(pattern.finditer(content))
if matches:
    count = 0

    def replace_block(_match):
        global count
        count += 1
        return new_block if count == 1 else ""

    updated = pattern.sub(replace_block, content)
    print(f"Updated finish-issue shell function in {rc_file}.")
else:
    separator = "" if not content else ("" if content.endswith("\n\n") else "\n" if content.endswith("\n") else "\n\n")
    updated = content + separator + new_block + "\n"
    print(f"Added finish-issue shell function to {rc_file}.")

with open(rc_file, "w") as file:
    file.write(updated)
PYEOF
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
