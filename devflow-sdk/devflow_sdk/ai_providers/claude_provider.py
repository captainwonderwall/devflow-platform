from devflow_sdk.ai_providers.base import AiProvider, parse_provider_output


class ClaudeProvider(AiProvider):
    name = "claude"
    binary = "claude"
    display_name = "Claude"
    install_hint = "https://claude.ai/code"
    models = {
        "fast": "claude-haiku-4-5-20251001",
        "capable": "claude-sonnet-4-6",
    }
    pricing = {
        "claude-haiku-4-5": {
            "input": 1.00, "output": 5.00,
            "cache_read": 0.10, "cache_write": 1.25,
        },
        "claude-sonnet-4-6": {
            "input": 3.00, "output": 15.00,
            "cache_read": 0.30, "cache_write": 3.75,
        },
    }

    def build_command(self, prompt, model, session_id, stateless, trust_level):
        cmd = ["claude", "-p", prompt, "--output-format", "json", "--model", model]
        if session_id:
            cmd += ["--resume", session_id]
        if stateless:
            cmd.append("--no-session-persistence")
        if trust_level == "full":
            cmd += ["--permission-mode", "bypassPermissions"]
        return cmd

    def parse_output(self, stdout, stderr, returncode, model):
        return parse_provider_output(stdout, stderr, returncode, model,
                                      provider_label="Claude", as_json=True)

    def parse_text_output(self, stdout, stderr, returncode, model):
        """Same as parse_output but returns the raw result text instead of
        attempting JSON parsing. Used when result_type='text'."""
        return parse_provider_output(stdout, stderr, returncode, model,
                                      provider_label="Claude", as_json=False)

    def build_interactive_command(self, initial_prompt: str) -> list[str]:
        return ["claude", initial_prompt]

    def build_interactive_resume_command(self, session_id: str | None) -> list[str]:
        cmd = ["claude", "--permission-mode", "bypassPermissions"]
        if session_id:
            cmd += ["--resume", session_id]
        else:
            cmd += ["--continue"]
        return cmd
