import os
import shlex
import stat


def write_create_script(title, body_path, script_path):
    safe_title = shlex.quote(title)
    safe_body = shlex.quote(body_path)
    script = f"""\
#!/bin/bash
set -euo pipefail

command -v gh &>/dev/null || {{ echo "gh CLI not found. Install from https://cli.github.com/"; exit 1; }}
gh auth status &>/dev/null 2>&1 || {{ echo "Not logged in. Run: gh auth login"; exit 1; }}

git push -u origin HEAD

gh pr create \\
  --draft \\
  --title {safe_title} \\
  --body-file {safe_body} \\
  --head "$(git branch --show-current)"
"""
    with open(script_path, "w") as f:
        f.write(script)
    os.chmod(script_path, os.stat(script_path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
