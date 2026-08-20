import json
import subprocess
import sys

WORKTRUNK_INSTALL_HINT = (
    "ERROR: worktrunk (wt) not found. Install it with:\n"
    "  brew install worktrunk\n"
    "Then set up shell integration: wt config shell install"
)


def check_worktrunk() -> None:
    """Exit 1 with an install hint if the wt CLI is not available."""
    try:
        subprocess.run(["wt", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print(WORKTRUNK_INSTALL_HINT, file=sys.stderr)
        sys.exit(1)


def query_worktrees() -> list | None:
    """Return parsed wt list --format json output, or None on any failure."""
    try:
        result = subprocess.run(
            ["wt", "list", "--format", "json"],
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def list_worktrees() -> list:
    """Return the parsed wt list --format json payload, or exit 1 on failure."""
    try:
        result = subprocess.run(
            ["wt", "list", "--format", "json"],
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        print(WORKTRUNK_INSTALL_HINT, file=sys.stderr)
        sys.exit(1)
    if result.returncode != 0:
        print(f"ERROR: 'wt list' failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"ERROR: 'wt list' returned invalid JSON:\n{result.stdout}", file=sys.stderr)
        sys.exit(1)
