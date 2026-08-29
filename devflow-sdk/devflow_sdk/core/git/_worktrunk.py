# devflow_sdk/core/git/_worktrunk.py
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
