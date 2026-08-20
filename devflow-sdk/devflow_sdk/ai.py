import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import Literal

from devflow_sdk.ai_providers import get_provider
from devflow_sdk.ai_providers.base import AiResult
from devflow_sdk.config import load_config
from devflow_sdk.cost import accumulator

__all__ = ["run_ai_prompt", "launch_interactive_session", "AiResult"]

_DATE_SUFFIX_RE = re.compile(r'-\d{8}$')


def _write_debug_log(provider, cmd: list, returncode: int,
                      stdout: str, stderr: str) -> None:
    """Write the raw command, exit code, stdout, and stderr from an AI CLI
    invocation to a temp file so it can be inspected even when the output
    can't be parsed into a usable result (e.g. the CLI crashed, hit a
    permission prompt, or never produced the expected tags)."""
    tmp = tempfile.NamedTemporaryFile(
        prefix=f"{provider.name}-debug-", suffix=".log", delete=False, mode="w"
    )
    safe_cmd = provider.redact_command(cmd)
    tmp.write(f"=== COMMAND ===\n{shlex.join(safe_cmd)}\n\n")
    tmp.write(f"=== EXIT CODE ===\n{returncode}\n\n")
    tmp.write(f"=== STDOUT ===\n{stdout}\n\n")
    tmp.write(f"=== STDERR ===\n{stderr}\n")
    tmp.close()
    print(f"{provider.display_name} debug output saved to {tmp.name}",
          file=sys.stderr)


def launch_interactive_session(
    initial_prompt: str,
    cwd: str | None = None,
) -> None:
    try:
        config = load_config()
    except ValueError as exc:
        print(f"WARNING: {exc}", file=sys.stderr)
        return
    try:
        provider = get_provider(config)
    except ValueError as exc:
        print(f"WARNING: {exc}", file=sys.stderr)
        return

    if shutil.which(provider.binary) is None:
        hint = f" Install from {provider.install_hint}" if provider.install_hint else ""
        print(f"WARNING: {provider.binary} CLI not found.{hint}", file=sys.stderr)
        return

    cmd = provider.build_interactive_command(initial_prompt)
    subprocess.run(cmd, cwd=cwd)


def run_ai_prompt(
    prompt: str,
    tier: Literal["fast", "capable"],
    result_type: Literal["json", "text"] = "json",
    session_id: str | None = None,
    stateless: bool = False,
    trust_level: Literal["default", "full"] = "default",
    cwd: str | None = None,
    debug: bool = False,
) -> AiResult:
    try:
        config = load_config()
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    try:
        provider = get_provider(config)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if shutil.which(provider.binary) is None:
        hint = f" Install from {provider.install_hint}" if provider.install_hint else ""
        print(
            f"ERROR: {provider.binary} CLI not found.{hint}",
            file=sys.stderr,
        )
        sys.exit(1)

    if tier not in provider.models:
        allowed = ", ".join(sorted(provider.models.keys()))
        print(
            f"ERROR: tier '{tier}' is not supported by provider "
            f"'{provider.name}' (allowed: {allowed}).",
            file=sys.stderr,
        )
        sys.exit(1)

    model = provider.models[tier]
    base_model = _DATE_SUFFIX_RE.sub('', model)
    if base_model not in provider.pricing:
        allowed = ", ".join(sorted(provider.pricing.keys()))
        print(
            f"ERROR: model '{model}' is not in the allowed set ({allowed}).",
            file=sys.stderr,
        )
        sys.exit(1)

    cmd = provider.build_command(prompt, model, session_id, stateless, trust_level)

    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    if debug:
        _write_debug_log(provider, cmd, proc.returncode, stdout, stderr)

    if result_type == "json":
        result = provider.parse_output(stdout, stderr, proc.returncode, model)
    else:
        result = provider.parse_text_output(stdout, stderr, proc.returncode, model)

    accumulator.add(result.usage, model, provider.pricing)

    return result
