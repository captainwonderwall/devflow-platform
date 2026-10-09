import sys

_GRAY = "\033[90m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_RESET = "\033[0m"


def status(msg):
    print(f"{_GRAY}→{_RESET} {msg}")


def success(msg):
    print(f"{_GREEN}✓{_RESET} {msg}")


def error(msg, file=None):
    print(f"{_RED}✗{_RESET} {msg}", file=file or sys.stderr)


def info(msg):
    print(msg)
