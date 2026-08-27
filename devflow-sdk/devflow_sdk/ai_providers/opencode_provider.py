from devflow_sdk.ai_providers.base import AiProvider, parse_provider_output


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
        return parse_provider_output(
            stdout, stderr, returncode, model,
            provider_label="OpenCode", as_json=True,
            result_keys=("result", "text"),
            session_keys=("session_id", "sessionID"),
        )

    def parse_text_output(self, stdout, stderr, returncode, model):
        return parse_provider_output(
            stdout, stderr, returncode, model,
            provider_label="OpenCode", as_json=False,
            result_keys=("result", "text"),
            session_keys=("session_id", "sessionID"),
        )

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
