from devflow_sdk.ai_providers.base import AiProvider, AiResult
from devflow_sdk.config import GlobalConfig, ModelConfig


def test_ai_provider_is_abstract():
    import pytest
    with pytest.raises(TypeError):
        AiProvider()


def test_ai_result_defaults_total_tokens_to_zero():
    result = AiResult(result="x", session_id=None, ok=True, error="", needs_interaction=False)
    assert result.total_tokens == 0


from devflow_sdk.ai_providers.claude_provider import ClaudeProvider


def test_claude_build_command_basic():
    provider = ClaudeProvider()
    cmd = provider.build_command("hello", "claude-haiku-4-5-20251001",
                                  session_id=None, stateless=False, trust_level="default")
    assert cmd == ["claude", "-p", "hello", "--output-format", "json",
                   "--model", "claude-haiku-4-5-20251001"]


def test_claude_build_command_with_resume():
    provider = ClaudeProvider()
    cmd = provider.build_command("hello", "claude-haiku-4-5-20251001",
                                  session_id="sess-1", stateless=False, trust_level="default")
    assert "--resume" in cmd
    assert "sess-1" in cmd


def test_claude_build_command_stateless():
    provider = ClaudeProvider()
    cmd = provider.build_command("hello", "claude-haiku-4-5-20251001",
                                  session_id=None, stateless=True, trust_level="default")
    assert "--no-session-persistence" in cmd


def test_claude_build_command_trust_full():
    provider = ClaudeProvider()
    cmd = provider.build_command("hello", "claude-haiku-4-5-20251001",
                                  session_id=None, stateless=False, trust_level="full")
    assert "--permission-mode" in cmd
    assert "bypassPermissions" in cmd


def test_claude_models_and_pricing():
    provider = ClaudeProvider()
    assert provider.name == "claude"
    assert provider.binary == "claude"
    assert provider.models == {"fast": "claude-haiku-4-5-20251001", "capable": "claude-sonnet-4-6"}
    assert "claude-haiku-4-5" in provider.pricing
    assert "claude-sonnet-4-6" in provider.pricing


def test_claude_parse_output_json_result():
    import json
    provider = ClaudeProvider()
    stdout = json.dumps({
        "result": json.dumps({"title": "My PR"}),
        "session_id": "sess-xyz",
        "usage": {"input_tokens": 100, "output_tokens": 50,
                  "cache_read_input_tokens": 0, "cache_write_input_tokens": 0},
        "model": "claude-haiku-4-5",
    })
    result = provider.parse_output(stdout, "", 0, "claude-haiku-4-5")
    assert result.ok is True
    assert result.result == {"title": "My PR"}
    assert result.session_id == "sess-xyz"
    assert result.total_tokens == 150


def test_claude_parse_output_nonzero_returncode():
    provider = ClaudeProvider()
    result = provider.parse_output("", "some error", 1, "claude-haiku-4-5")
    assert result.ok is False
    assert result.error == "some error"


def test_claude_parse_output_needs_interaction_in_stderr():
    provider = ClaudeProvider()
    result = provider.parse_output("", "permission prompts are waiting", 1,
                                    "claude-haiku-4-5")
    assert result.needs_interaction is True


def test_claude_parse_output_nonzero_returncode_still_captures_usage():
    provider = ClaudeProvider()
    stdout = ('{"is_error": true, "result": "",'
              ' "usage": {"input_tokens": 10, "output_tokens": 5}}')
    result = provider.parse_output(stdout, "", 1, "claude-haiku-4-5")
    assert result.ok is False
    assert result.usage == {"input_tokens": 10, "output_tokens": 5}


import json
from devflow_sdk.ai_providers.opencode_provider import OpenCodeProvider


def test_opencode_build_command_basic():
    provider = OpenCodeProvider()
    cmd = provider.build_command("hello", "github-copilot/claude-sonnet-4-5", session_id=None,
                                  stateless=True, trust_level="default")
    assert cmd == ["opencode", "run", "hello", "--format", "json", "--model", "github-copilot/claude-sonnet-4-5"]


def test_opencode_build_command_with_session():
    provider = OpenCodeProvider()
    cmd = provider.build_command("hello", "github-copilot/claude-sonnet-4-5", session_id="sess-1",
                                  stateless=False, trust_level="default")
    assert "--session" in cmd
    assert "sess-1" in cmd


def test_opencode_build_command_trust_full():
    provider = OpenCodeProvider()
    cmd = provider.build_command("hello", "github-copilot/claude-sonnet-4-5", session_id=None,
                                  stateless=True, trust_level="full")
    assert "--auto" in cmd


def test_opencode_models_and_pricing():
    provider = OpenCodeProvider()
    assert provider.name == "opencode"
    assert provider.binary == "opencode"
    assert set(provider.models.keys()) == {"fast", "capable"}
    for model_id in provider.models.values():
        assert model_id in provider.pricing


def test_get_provider_resolves_configured_opencode_model_from_catalog():
    provider = get_provider(GlobalConfig(
        ai_provider="opencode",
        models={
            "fast": ModelConfig(name="github-copilot/gpt-5-mini"),
            "capable": ModelConfig(name="github-copilot/gpt-5.6-luna"),
        },
    ))

    assert provider.pricing["github-copilot/gpt-5-mini"] == {
        "input": 0.25,
        "output": 2.0,
        "cache_read": 0.025,
        "cache_write": None,
    }
    assert provider.models["capable"] == "github-copilot/gpt-5.6-luna"
    assert provider.pricing["github-copilot/gpt-5.6-luna"] == {
        "input": 0.2,
        "output": 1.2,
        "cache_read": 0.02,
        "cache_write": 0.25,
    }


def test_explicit_configured_pricing_takes_precedence_over_catalog():
    configured_pricing = {
        "input": 9.0,
        "output": 8.0,
        "cache_read": 7.0,
        "cache_write": 6.0,
    }
    provider = get_provider(GlobalConfig(
        ai_provider="opencode",
        models={"capable": ModelConfig(
            name="github-copilot/gpt-5.6-luna",
            pricing=configured_pricing,
        )},
    ))

    assert provider.pricing["github-copilot/gpt-5.6-luna"] == configured_pricing


def test_opencode_parse_output_json_result():
    provider = OpenCodeProvider()
    stdout = json.dumps({
        "result": json.dumps({"title": "My PR"}),
        "session_id": "sess-xyz",
        "usage": {"input_tokens": 100, "output_tokens": 50,
                  "cache_read_input_tokens": 0, "cache_write_input_tokens": 0},
    })
    result = provider.parse_output(stdout, "", 0, "github-copilot/claude-sonnet-4-5")
    assert result.ok is True
    assert result.result == {"title": "My PR"}
    assert result.session_id == "sess-xyz"
    assert result.total_tokens == 150


def test_opencode_parse_output_json_event_stream():
    stdout = "\n".join([
        json.dumps({"type": "step_start", "sessionID": "sess-xyz", "part": {}}),
        json.dumps({"type": "tool_use", "sessionID": "sess-xyz", "part": {}}),
        json.dumps({
            "type": "text", "sessionID": "sess-xyz",
            "part": {"type": "text", "text": '{"title":"My PR"}'},
        }),
        json.dumps({"type": "step_finish", "sessionID": "sess-xyz", "part": {}}),
    ])
    result = OpenCodeProvider().parse_output(
        stdout, "", 0, "github-copilot/claude-sonnet-4-5"
    )
    assert result.ok is True
    assert result.result == {"title": "My PR"}
    assert result.session_id == "sess-xyz"


def test_opencode_parse_output_json_event_error():
    stdout = json.dumps({
        "type": "error",
        "sessionID": "sess-xyz",
        "error": {"name": "UnknownError", "data": {"message": "provider failed"}},
    })
    result = OpenCodeProvider().parse_output(
        stdout, "", 1, "github-copilot/claude-sonnet-4-5"
    )
    assert result.ok is False
    assert result.error == "provider failed"
    assert result.session_id == "sess-xyz"


def test_opencode_parse_output_nonzero_returncode():
    provider = OpenCodeProvider()
    result = provider.parse_output("", "some error", 1, "github-copilot/claude-sonnet-4-5")
    assert result.ok is False
    assert result.error == "some error"


import pytest
from devflow_sdk.ai_providers import get_provider


def test_get_provider_claude():
    provider = get_provider(GlobalConfig(ai_provider="claude"))
    assert provider.name == "claude"


def test_get_provider_opencode():
    provider = get_provider(GlobalConfig(ai_provider="opencode"))
    assert provider.name == "opencode"


def test_get_provider_unknown_raises_with_valid_names_listed():
    with pytest.raises(ValueError, match="claude"):
        get_provider(GlobalConfig(ai_provider="bogus"))


def test_parse_provider_output_non_dict_json_array_does_not_raise():
    from devflow_sdk.ai_providers.base import parse_provider_output
    result = parse_provider_output("[]", "", 0, "claude-haiku-4-5",
                                    provider_label="Claude", as_json=True)
    assert result.ok is False


def test_opencode_redact_command_redacts_positional_prompt():
    provider = OpenCodeProvider()
    cmd = ["opencode", "run", "SECRET PROMPT TEXT", "--format", "json"]
    redacted = provider.redact_command(cmd)
    assert "SECRET PROMPT TEXT" not in redacted
    assert redacted[2] == "<redacted>"


def test_claude_build_interactive_command_includes_prompt():
    provider = ClaudeProvider()
    cmd = provider.build_interactive_command("Brainstorm a solution")
    assert cmd == ["claude", "Brainstorm a solution"]


def test_opencode_build_interactive_command_includes_prompt():
    provider = OpenCodeProvider()
    cmd = provider.build_interactive_command("Brainstorm a solution")
    assert cmd == ["opencode", "--prompt", "Brainstorm a solution"]


class TestProviderAttributes:
    def test_claude_models_dev_key(self):
        assert ClaudeProvider().models_dev_key == "anthropic"

    def test_claude_models_dev_id_prefix(self):
        assert ClaudeProvider().models_dev_id_prefix == ""

    def test_opencode_models_dev_key(self):
        assert OpenCodeProvider().models_dev_key == "github-copilot"

    def test_opencode_models_dev_id_prefix(self):
        assert OpenCodeProvider().models_dev_id_prefix == "github-copilot/"
