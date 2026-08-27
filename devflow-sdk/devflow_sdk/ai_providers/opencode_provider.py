import json

from devflow_sdk.ai_providers.base import AiProvider, AiResult, parse_provider_output


def _parse_event_stream(stdout, stderr, returncode, model, as_json):
    """Parse OpenCode's newline-delimited events from `run --format json`."""
    try:
        events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
    except json.JSONDecodeError:
        return parse_provider_output(
            stdout, stderr, returncode, model,
            provider_label="OpenCode", as_json=as_json,
            result_keys=("result", "text"),
            session_keys=("session_id", "sessionID"),
        )

    if not events or not all(isinstance(event, dict) for event in events):
        return parse_provider_output(
            stdout, stderr, returncode, model,
            provider_label="OpenCode", as_json=as_json,
            result_keys=("result", "text"),
            session_keys=("session_id", "sessionID"),
        )

    session_id = next(
        (event.get(key) for event in events for key in ("sessionID", "session_id")
         if event.get(key)),
        None,
    )
    errors = [event for event in events if event.get("type") == "error"]
    if errors:
        error = errors[-1].get("error", errors[-1])
        if isinstance(error, dict):
            data = error.get("data")
            error = (data or {}).get("message") or error.get("name") or str(error)
        return AiResult(
            result={} if as_json else "", session_id=session_id, ok=False,
            error=str(error), needs_interaction=False,
        )

    text_parts = [
        event["part"].get("text", "")
        for event in events
        if event.get("type") == "text"
        and isinstance(event.get("part"), dict)
        and isinstance(event["part"].get("text"), str)
    ]
    if not text_parts:
        return parse_provider_output(
            stdout, stderr, returncode, model,
            provider_label="OpenCode", as_json=as_json,
            result_keys=("result", "text"),
            session_keys=("session_id", "sessionID"),
        )

    synthetic = json.dumps({"text": "\n".join(text_parts), "sessionID": session_id})
    return parse_provider_output(
        synthetic, stderr, returncode, model,
        provider_label="OpenCode", as_json=as_json,
        result_keys=("result", "text"), session_keys=("session_id", "sessionID"),
    )


class OpenCodeProvider(AiProvider):
    """OpenCode CLI backend using GitHub Copilot models."""

    name = "opencode"
    binary = "opencode"
    display_name = "OpenCode"
    install_hint = "https://opencode.ai"
    models_dev_key = "github-copilot"
    models_dev_id_prefix = "github-copilot/"
    models = {
        "fast": "github-copilot/claude-sonnet-4-5",
        "capable": "github-copilot/claude-sonnet-4-6",
    }
    pricing = {
        "github-copilot/claude-sonnet-4-5": {
            "input": 3.00, "output": 15.00,
            "cache_read": 0.30, "cache_write": 3.75,
        },
        "github-copilot/claude-sonnet-4-6": {
            "input": 3.00, "output": 15.00,
            "cache_read": 0.30, "cache_write": 3.75,
        },
    }

    def build_command(self, prompt, model, session_id, stateless, trust_level):
        # `stateless` is intentionally not passed as a flag: OpenCode is
        # stateless-by-default unless a `--session` id is supplied.
        cmd = ["opencode", "run", prompt, "--format", "json", "--model", model]
        if session_id:
            cmd += ["--session", session_id]
        if trust_level == "full":
            cmd.append("--auto")
        return cmd

    def redact_command(self, cmd: list) -> list:
        safe_cmd = list(cmd)
        if len(safe_cmd) > 2:
            safe_cmd[2] = "<redacted>"
        return safe_cmd

    def parse_output(self, stdout, stderr, returncode, model):
        return _parse_event_stream(stdout, stderr, returncode, model, as_json=True)

    def parse_text_output(self, stdout, stderr, returncode, model):
        return _parse_event_stream(stdout, stderr, returncode, model, as_json=False)

    def build_interactive_command(self, initial_prompt: str) -> list[str]:
        cmd = ["opencode"]
        if initial_prompt:
            cmd += ["--prompt", initial_prompt]
        return cmd

    def build_interactive_resume_command(self, session_id: str | None) -> list[str]:
        cmd = ["opencode", "--auto"]
        if session_id:
            cmd += ["--session", session_id]
        return cmd
