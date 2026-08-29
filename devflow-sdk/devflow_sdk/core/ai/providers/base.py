import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AiResult:
    result: Any
    session_id: str | None
    ok: bool
    error: str
    needs_interaction: bool
    total_tokens: int = 0
    usage: dict = field(default_factory=dict)


class AiProvider(ABC):
    name: str
    binary: str
    models: dict[str, str]
    pricing: dict[str, dict]
    install_hint: str = ""
    display_name: str = ""
    redact_after_flags: tuple = ("-p",)
    models_dev_key: str = ""
    models_dev_id_prefix: str = ""

    @abstractmethod
    def build_command(
        self,
        prompt: str,
        model: str,
        session_id: str | None,
        stateless: bool,
        trust_level: str,
    ) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def parse_output(
        self,
        stdout: str,
        stderr: str,
        returncode: int,
        model: str,
    ) -> AiResult:
        raise NotImplementedError

    @abstractmethod
    def parse_text_output(
        self,
        stdout: str,
        stderr: str,
        returncode: int,
        model: str,
    ) -> AiResult:
        raise NotImplementedError

    @abstractmethod
    def build_interactive_command(self, initial_prompt: str) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def build_interactive_resume_command(self, session_id: str | None) -> list[str]:
        raise NotImplementedError

    def redact_command(self, cmd: list) -> list:
        """Return a copy of cmd with prompt/sensitive arguments redacted for
        safe logging. Default: redact the argument following any flag in
        `redact_after_flags` (e.g. Claude's `-p <prompt>`)."""
        safe_cmd = []
        skip_next = False
        for arg in cmd:
            if skip_next:
                safe_cmd.append("<redacted>")
                skip_next = False
            elif arg in self.redact_after_flags:
                safe_cmd.append(arg)
                skip_next = True
            else:
                safe_cmd.append(arg)
        return safe_cmd


PERMISSION_STRINGS = ("waiting for your approval", "permission prompts are waiting")


def _parse_json_text(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r'```(?:json)?\n([\s\S]*?)\n```', text)
    if match:
        return json.loads(match.group(1))
    raise json.JSONDecodeError("No valid JSON found in provider output", text, 0)


def _first_present(outer: dict, keys: tuple) -> Any:
    for key in keys:
        value = outer.get(key)
        if value:
            return value
    return None


def parse_provider_output(stdout: str, stderr: str, returncode: int, model: str, *,
                           provider_label: str, as_json: bool,
                           result_keys: tuple = ("result",),
                           session_keys: tuple = ("session_id",)) -> AiResult:
    empty_result = {} if as_json else ""

    if returncode != 0:
        combined = stderr + stdout
        ni = any(s in combined for s in PERMISSION_STRINGS)
        error = stderr or stdout
        usage = {}
        try:
            outer = json.loads(stdout)
        except json.JSONDecodeError:
            outer = None
        if isinstance(outer, dict):
            usage = outer.get("usage") or {}
        return AiResult(result=empty_result, session_id=None, ok=False, error=error,
                         needs_interaction=ni, usage=usage)

    try:
        outer = json.loads(stdout)
    except json.JSONDecodeError:
        ni = any(s in stdout for s in PERMISSION_STRINGS)
        return AiResult(result=empty_result, session_id=None, ok=False, error=stdout,
                         needs_interaction=ni, usage={})

    if not isinstance(outer, dict):
        ni = any(s in stdout for s in PERMISSION_STRINGS)
        return AiResult(result=empty_result, session_id=None, ok=False, error=stdout,
                         needs_interaction=ni, usage={})

    raw = _first_present(outer, result_keys)
    raw_result: Any = raw.strip() if isinstance(raw, str) else (raw if raw is not None else "")
    out_session_id = _first_present(outer, session_keys)
    usage = outer.get("usage") or {}

    total_tokens = (
        usage.get("input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
        + usage.get("output_tokens", 0)
    )

    result_str = raw_result if isinstance(raw_result, str) else ""
    ni = any(s in t for s in PERMISSION_STRINGS for t in (result_str, stderr))

    if not as_json:
        return AiResult(result=raw_result, session_id=out_session_id, ok=True,
                         error=stderr, needs_interaction=ni, total_tokens=total_tokens,
                         usage=usage)

    if not isinstance(raw_result, str):
        return AiResult(result=raw_result, session_id=out_session_id, ok=True,
                         error=stderr, needs_interaction=ni, total_tokens=total_tokens,
                         usage=usage)

    try:
        result_value = _parse_json_text(raw_result)
    except json.JSONDecodeError:
        return AiResult(
            result={}, session_id=out_session_id, ok=False,
            error=f"Could not parse JSON from {provider_label} result: {raw_result[:200]}",
            needs_interaction=ni, total_tokens=total_tokens, usage=usage,
        )

    return AiResult(result=result_value, session_id=out_session_id, ok=True,
                     error=stderr, needs_interaction=ni, total_tokens=total_tokens,
                     usage=usage)
