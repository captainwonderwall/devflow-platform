#!/usr/bin/env python3
import argparse
import os
import pathlib
import subprocess
import sys
import tempfile
import uuid

_IMAGE = "minlag/mermaid-cli"
_FORMATS = ("png", "svg", "pdf")
_THEMES = ("default", "forest", "dark", "neutral")
_INSPECT_TIMEOUT = 10
_RENDER_TIMEOUT = 60
_PULL_TIMEOUT = 300


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
    try:
        inspect_result = subprocess.run(
            ["docker", "image", "inspect", _IMAGE],
            capture_output=True,
            timeout=_INSPECT_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        sys.exit("Error: Docker daemon not responding.")
    if inspect_result.returncode != 0:
        print(f"Pulling {_IMAGE}...", file=sys.stderr)
        try:
            subprocess.run(
                ["docker", "pull", _IMAGE],
                check=True,
                stdout=sys.stderr,
                timeout=_PULL_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            sys.exit(f"Error: timed out pulling Docker image '{_IMAGE}'.")
        except subprocess.CalledProcessError:
            sys.exit(f"Error: failed to pull Docker image '{_IMAGE}'.")


def _render(source: bytes, format: str, theme: str) -> bytes:
    with tempfile.TemporaryDirectory() as tmpdir:
        out_name = f"out.{format}"
        container_name = f"diagram-{uuid.uuid4().hex[:12]}"
        cmd = [
            "docker", "run", "--rm", "-i",
            "--name", container_name,
            "-u", f"{os.getuid()}:{os.getgid()}",
            "-v", f"{tmpdir}:/output",
            _IMAGE,
            "-i", "-", "-o", f"/output/{out_name}", "-e", format,
        ]
        if theme != "default":
            cmd += ["-t", theme]
        try:
            result = subprocess.run(
                cmd, input=source, capture_output=True, timeout=_RENDER_TIMEOUT
            )
        except subprocess.TimeoutExpired:
            try:
                subprocess.run(
                    ["docker", "kill", container_name],
                    capture_output=True,
                    timeout=5,
                )
            except Exception:
                pass
            sys.exit("Error: rendering timed out.")
        if result.returncode != 0:
            sys.stderr.buffer.write(result.stderr)
            sys.exit(result.returncode)
        out_path = pathlib.Path(tmpdir, out_name)
        if not out_path.exists():
            sys.exit(
                f"Error: mermaid-cli did not write /output/{out_name}. "
                f"Ensure your Docker runtime shares the host temp directory "
                f"(e.g. add {tmpdir!r} to File Sharing in Docker Desktop)."
            )
        return out_path.read_bytes()


def main():
    args = parse_args()
    if sys.stdin.isatty():
        sys.exit("Error: pipe Mermaid source to stdin, e.g.:  echo 'graph TD; A-->B' | diagram")
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
