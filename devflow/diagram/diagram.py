#!/usr/bin/env python3
import argparse
import subprocess
import sys

_IMAGE = "minlag/mermaid-cli"
_FORMATS = ("png", "svg", "pdf")
_THEMES = ("default", "forest", "dark", "neutral")


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Render a Mermaid diagram from stdin via Docker."
    )
    p.add_argument("--format", "-f", choices=_FORMATS, default="png")
    p.add_argument("--theme", "-t", choices=_THEMES, default="default")
    p.add_argument("--output", "-o", default=None, metavar="PATH")
    return p.parse_args(argv)


def _ensure_docker():
    if subprocess.run(["which", "docker"], capture_output=True).returncode != 0:
        sys.exit("Error: docker is not installed or not on PATH.")


def _ensure_image():
    if subprocess.run(
        ["docker", "image", "inspect", _IMAGE], capture_output=True
    ).returncode != 0:
        print(f"Pulling {_IMAGE}...", file=sys.stderr)
        try:
            subprocess.run(["docker", "pull", _IMAGE], check=True, stdout=sys.stderr)
        except subprocess.CalledProcessError:
            sys.exit(f"Error: failed to pull Docker image '{_IMAGE}'.")


def _render(source: bytes, format: str, theme: str) -> bytes:
    cmd = [
        "docker", "run", "--rm", "-i",
        _IMAGE,
        "-i", "-", "-o", "/dev/stdout", "-e", format,
    ]
    if theme != "default":
        cmd += ["-t", theme]
    result = subprocess.run(cmd, input=source, capture_output=True)
    if result.returncode != 0:
        sys.stderr.buffer.write(result.stderr)
        sys.exit(result.returncode)
    return result.stdout


def main():
    args = parse_args()
    source = sys.stdin.buffer.read()
    if not source.strip():
        sys.exit("Error: no Mermaid source on stdin.")
    _ensure_docker()
    _ensure_image()
    image_bytes = _render(source, args.format, args.theme)
    if args.output:
        with open(args.output, "wb") as f:
            f.write(image_bytes)
    else:
        sys.stdout.buffer.write(image_bytes)


if __name__ == "__main__":
    main()
