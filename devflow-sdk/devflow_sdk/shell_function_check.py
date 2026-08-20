import os
import sys


def check_shell_function(sentinel: str, install_hint: str, *, required_content: str | None = None) -> None:
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

    if sentinel not in content:
        print(install_hint, file=sys.stderr)
        sys.exit(1)

    if required_content is not None:
        fragments = [required_content] if isinstance(required_content, str) else required_content
        if any(frag not in content for frag in fragments):
            print(install_hint, file=sys.stderr)
            sys.exit(1)
