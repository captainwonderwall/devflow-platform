import os
import re
import sys
from collections.abc import Sequence


def check_shell_function(
    sentinel: str,
    install_hint: str,
    *,
    required_content: str | Sequence[str] | None = None,
) -> None:
    shell = os.environ.get("SHELL", "")
    shell_name = os.path.basename(shell)

    if shell_name == "zsh":
        rc_path = os.path.expanduser("~/.zshrc")
    elif shell_name == "bash":
        rc_path = os.path.expanduser("~/.bashrc")
    else:
        print(install_hint, file=sys.stderr)
        sys.exit(1)

    try:
        content = open(rc_path).read()
    except OSError:
        print(install_hint, file=sys.stderr)
        sys.exit(1)

    end_sentinel = sentinel.replace("# >>>", "# <<<").replace(">>>", "<<<")
    block_pattern = re.compile(
        re.escape(sentinel) + r"(.*?)" + re.escape(end_sentinel),
        flags=re.DOTALL,
    )
    match = block_pattern.search(content)
    if match is None:
        print(install_hint, file=sys.stderr)
        sys.exit(1)

    if required_content is not None:
        fragments = [required_content] if isinstance(required_content, str) else required_content
        if any(frag not in match.group(1) for frag in fragments):
            print(install_hint, file=sys.stderr)
            sys.exit(1)
