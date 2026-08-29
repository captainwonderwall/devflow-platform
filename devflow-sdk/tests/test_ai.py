import json
import pytest
from unittest.mock import patch, MagicMock

from devflow_sdk.core.ai import run_ai_prompt, AiResult


@pytest.fixture(autouse=True)
def _no_devflow_config(tmp_path, monkeypatch):
    monkeypatch.setattr("devflow_sdk.core.config.io.CONFIG_PATH", tmp_path / "config.json")


def _mock_proc(result_str, session_id="sess-1", returncode=0, stderr="",
               input_tokens=100, output_tokens=50, model="claude-haiku-4-5"):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = json.dumps({
        "result": result_str,
        "session_id": session_id,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_input_tokens": 0,
            "cache_write_input_tokens": 0,
        },
        "model": model,
    })
    m.stderr = stderr
    return m


def test_returns_parsed_json_result():
    payload = {"title": "My PR"}
    with patch("devflow_sdk.core.ai.shutil.which", return_value="/usr/bin/claude"), \
         patch("devflow_sdk.core.ai.subprocess.run", return_value=_mock_proc(json.dumps(payload))):
        result = run_ai_prompt("prompt", tier="fast", result_type="json")
    assert result.result == payload
    assert result.ok is True


def test_returns_text_result():
    with patch("devflow_sdk.core.ai.shutil.which", return_value="/usr/bin/claude"), \
         patch("devflow_sdk.core.ai.subprocess.run", return_value=_mock_proc("<edits></edits>")):
        result = run_ai_prompt("prompt", tier="fast", result_type="text")
    assert result.result == "<edits></edits>"
    assert result.ok is True


def test_session_id_returned():
    with patch("devflow_sdk.core.ai.shutil.which", return_value="/usr/bin/claude"), \
         patch("devflow_sdk.core.ai.subprocess.run", return_value=_mock_proc("{}", session_id="sess-xyz")):
        result = run_ai_prompt("prompt", tier="fast")
    assert result.session_id == "sess-xyz"


def test_resume_flag_added_when_session_id_given():
    with patch("devflow_sdk.core.ai.shutil.which", return_value="/usr/bin/claude"), \
         patch("devflow_sdk.core.ai.subprocess.run", return_value=_mock_proc("{}")) as mock_run:
        run_ai_prompt("prompt", tier="fast", session_id="sess-abc")
    cmd = mock_run.call_args[0][0]
    assert "--resume" in cmd
    assert "sess-abc" in cmd


def test_stateless_flag_added():
    with patch("devflow_sdk.core.ai.shutil.which", return_value="/usr/bin/claude"), \
         patch("devflow_sdk.core.ai.subprocess.run", return_value=_mock_proc("{}")) as mock_run:
        run_ai_prompt("prompt", tier="fast", stateless=True)
    cmd = mock_run.call_args[0][0]
    assert "--no-session-persistence" in cmd


def test_trust_level_full_adds_bypass_permissions():
    with patch("devflow_sdk.core.ai.shutil.which", return_value="/usr/bin/claude"), \
         patch("devflow_sdk.core.ai.subprocess.run", return_value=_mock_proc("{}")) as mock_run:
        run_ai_prompt("prompt", tier="fast", trust_level="full")
    cmd = mock_run.call_args[0][0]
    assert "--permission-mode" in cmd
    assert "bypassPermissions" in cmd


def test_disallowed_tier_exits():
    with patch("devflow_sdk.core.ai.shutil.which", return_value="/usr/bin/claude"):
        with pytest.raises(SystemExit):
            run_ai_prompt("prompt", tier="ultra")


def test_claude_not_found_exits():
    with patch("devflow_sdk.core.ai.shutil.which", return_value=None):
        with pytest.raises(SystemExit):
            run_ai_prompt("prompt", tier="fast")


def test_unknown_ai_provider_config_exits(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text('{"ai_provider": "bogus"}')
    monkeypatch.setattr("devflow_sdk.core.config.io.CONFIG_PATH", cfg)
    with pytest.raises(SystemExit):
        run_ai_prompt("prompt", tier="fast")


def test_cost_tracked_via_accumulator():
    with patch("devflow_sdk.core.ai.shutil.which", return_value="/usr/bin/claude"), \
         patch("devflow_sdk.core.ai.subprocess.run", return_value=_mock_proc("{}", input_tokens=100)), \
         patch("devflow_sdk.core.ai.accumulator.add") as mock_add:
        run_ai_prompt("prompt", tier="fast")
    mock_add.assert_called_once()
    args, _ = mock_add.call_args
    usage_arg, model_arg, pricing_arg = args[0], args[1], args[2]
    assert usage_arg.get("input_tokens") == 100
    assert isinstance(pricing_arg, dict)
    assert "claude-haiku-4-5" in pricing_arg


def test_needs_interaction_detected_in_result_text():
    with patch("devflow_sdk.core.ai.shutil.which", return_value="/usr/bin/claude"), \
         patch("devflow_sdk.core.ai.subprocess.run",
               return_value=_mock_proc("waiting for your approval")):
        result = run_ai_prompt("prompt", tier="fast", result_type="text")
    assert result.needs_interaction is True


def test_needs_interaction_detected_in_stderr():
    m = MagicMock()
    m.returncode = 0
    m.stdout = json.dumps({"result": "", "session_id": None,
                            "usage": {}, "model": "claude-haiku-4-5"})
    m.stderr = "permission prompts are waiting"
    with patch("devflow_sdk.core.ai.shutil.which", return_value="/usr/bin/claude"), \
         patch("devflow_sdk.core.ai.subprocess.run", return_value=m):
        result = run_ai_prompt("prompt", tier="fast", result_type="text")
    assert result.needs_interaction is True


def test_strips_markdown_fences_from_json_result():
    payload = {"key": "value"}
    fenced = f"```json\n{json.dumps(payload)}\n```"
    with patch("devflow_sdk.core.ai.shutil.which", return_value="/usr/bin/claude"), \
         patch("devflow_sdk.core.ai.subprocess.run", return_value=_mock_proc(fenced)):
        result = run_ai_prompt("prompt", tier="fast", result_type="json")
    assert result.result == payload


def test_capable_tier_resolves_to_sonnet_model():
    with patch("devflow_sdk.core.ai.shutil.which", return_value="/usr/bin/claude"), \
         patch("devflow_sdk.core.ai.subprocess.run", return_value=_mock_proc("{}")) as mock_run:
        result = run_ai_prompt("prompt", tier="capable")
    cmd = mock_run.call_args[0][0]
    assert "claude-sonnet-4-6" in cmd
    assert result.ok is True


def test_configured_catalog_model_is_allowed(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        '{"global": {"ai_provider": "opencode", "models": '
        '{"capable": {"name": "github-copilot/gpt-5.6-luna"}}}}'
    )
    monkeypatch.setattr("devflow_sdk.core.config.io.CONFIG_PATH", config_path)
    proc = _mock_proc("{}", model="github-copilot/gpt-5.6-luna")

    with patch("devflow_sdk.core.ai.shutil.which", return_value="/usr/bin/opencode"), \
         patch("devflow_sdk.core.ai.subprocess.run", return_value=proc) as mock_run:
        result = run_ai_prompt("prompt", tier="capable")

    assert result.ok is True
    assert "github-copilot/gpt-5.6-luna" in mock_run.call_args.args[0]


def test_not_ok_when_returncode_nonzero():
    m = MagicMock()
    m.returncode = 1
    m.stdout = ""
    m.stderr = "some error"
    with patch("devflow_sdk.core.ai.shutil.which", return_value="/usr/bin/claude"), \
         patch("devflow_sdk.core.ai.subprocess.run", return_value=m):
        result = run_ai_prompt("prompt", tier="fast")
    assert result.ok is False
    assert result.error == "some error"


def test_total_tokens_summed():
    proc = _mock_proc("{}", input_tokens=500, output_tokens=100)
    with patch("devflow_sdk.core.ai.shutil.which", return_value="/usr/bin/claude"), \
         patch("devflow_sdk.core.ai.subprocess.run", return_value=proc), \
         patch("devflow_sdk.core.ai.accumulator.add"):
        result = run_ai_prompt("prompt", tier="fast")
    assert result.total_tokens == 600


def test_json_parse_failure_returns_not_ok():
    with patch("devflow_sdk.core.ai.shutil.which", return_value="/usr/bin/claude"), \
         patch("devflow_sdk.core.ai.subprocess.run", return_value=_mock_proc("not json at all")):
        result = run_ai_prompt("prompt", tier="fast", result_type="json")
    assert result.ok is False


def test_cwd_passed_to_subprocess():
    with patch("devflow_sdk.core.ai.shutil.which", return_value="/usr/bin/claude"), \
         patch("devflow_sdk.core.ai.subprocess.run", return_value=_mock_proc("{}")) as mock_run:
        run_ai_prompt("prompt", tier="fast", cwd="/some/repo")
    _, kwargs = mock_run.call_args
    assert kwargs.get("cwd") == "/some/repo"


def test_debug_writes_log_file_with_command_exitcode_stdout_stderr():
    m = MagicMock()
    m.returncode = 0
    m.stdout = json.dumps({"result": "hello", "session_id": "sess-1",
                           "usage": {}, "model": "claude-haiku-4-5"})
    m.stderr = "some stderr text"
    written = {}

    class _FakeFile:
        def __init__(self, path):
            self.name = path
        def write(self, data):
            written["content"] = written.get("content", "") + data
        def close(self):
            pass

    fake_path = "/tmp/claude-debug-fake.log"
    with patch("devflow_sdk.core.ai.shutil.which", return_value="/usr/bin/claude"), \
         patch("devflow_sdk.core.ai.subprocess.run", return_value=m), \
         patch("devflow_sdk.core.ai.tempfile.NamedTemporaryFile",
               return_value=_FakeFile(fake_path)):
        run_ai_prompt("prompt", tier="fast", result_type="text", debug=True)

    content = written["content"]
    assert "=== COMMAND ===" in content
    assert "claude" in content
    assert "=== EXIT CODE ===" in content
    assert "0" in content
    assert "=== STDOUT ===" in content
    assert m.stdout in content
    assert "=== STDERR ===" in content
    assert "some stderr text" in content


def test_debug_prints_saved_path_to_stderr(capsys):
    m = MagicMock()
    m.returncode = 0
    m.stdout = json.dumps({"result": "hello", "session_id": "sess-1",
                           "usage": {}, "model": "claude-haiku-4-5"})
    m.stderr = ""

    class _FakeFile:
        def __init__(self, path):
            self.name = path
        def write(self, data):
            pass
        def close(self):
            pass

    fake_path = "/tmp/claude-debug-fake.log"
    with patch("devflow_sdk.core.ai.shutil.which", return_value="/usr/bin/claude"), \
         patch("devflow_sdk.core.ai.subprocess.run", return_value=m), \
         patch("devflow_sdk.core.ai.tempfile.NamedTemporaryFile",
               return_value=_FakeFile(fake_path)):
        run_ai_prompt("prompt", tier="fast", debug=True)

    captured = capsys.readouterr()
    assert fake_path in captured.err


def test_debug_writes_log_even_when_claude_exits_nonzero():
    m = MagicMock()
    m.returncode = 1
    m.stdout = ""
    m.stderr = "boom"
    written = {}

    class _FakeFile:
        def __init__(self, path):
            self.name = path
        def write(self, data):
            written["content"] = written.get("content", "") + data
        def close(self):
            pass

    fake_path = "/tmp/claude-debug-fake.log"
    with patch("devflow_sdk.core.ai.shutil.which", return_value="/usr/bin/claude"), \
         patch("devflow_sdk.core.ai.subprocess.run", return_value=m), \
         patch("devflow_sdk.core.ai.tempfile.NamedTemporaryFile",
               return_value=_FakeFile(fake_path)):
        result = run_ai_prompt("prompt", tier="fast", debug=True)

    assert result.ok is False
    assert "=== EXIT CODE ===" in written["content"]
    assert "1" in written["content"]
    assert "boom" in written["content"]


def test_debug_writes_log_even_when_json_unparseable():
    m = MagicMock()
    m.returncode = 0
    m.stdout = "not json at all"
    m.stderr = ""
    written = {}

    class _FakeFile:
        def __init__(self, path):
            self.name = path
        def write(self, data):
            written["content"] = written.get("content", "") + data
        def close(self):
            pass

    fake_path = "/tmp/claude-debug-fake.log"
    with patch("devflow_sdk.core.ai.shutil.which", return_value="/usr/bin/claude"), \
         patch("devflow_sdk.core.ai.subprocess.run", return_value=m), \
         patch("devflow_sdk.core.ai.tempfile.NamedTemporaryFile",
               return_value=_FakeFile(fake_path)):
        result = run_ai_prompt("prompt", tier="fast", result_type="json", debug=True)

    assert result.ok is False
    assert "not json at all" in written["content"]


def test_no_debug_file_written_when_debug_false():
    with patch("devflow_sdk.core.ai.shutil.which", return_value="/usr/bin/claude"), \
         patch("devflow_sdk.core.ai.subprocess.run", return_value=_mock_proc("{}")), \
         patch("devflow_sdk.core.ai.tempfile.NamedTemporaryFile") as mock_tmp:
        run_ai_prompt("prompt", tier="fast")
    mock_tmp.assert_not_called()


def test_run_ai_prompt_handles_non_dict_json_stdout():
    m = MagicMock()
    m.returncode = 0
    m.stdout = "null"
    m.stderr = ""
    with patch("devflow_sdk.core.ai.shutil.which", return_value="/usr/bin/claude"), \
         patch("devflow_sdk.core.ai.subprocess.run", return_value=m):
        result = run_ai_prompt("prompt", tier="fast", result_type="json")
    assert result.ok is False


from devflow_sdk.core.ai import launch_interactive_session


def test_launch_interactive_session_builds_command_from_provider():
    with patch("devflow_sdk.core.ai.shutil.which", return_value="/usr/bin/claude"), \
         patch("devflow_sdk.core.ai.subprocess.run") as mock_run:
        launch_interactive_session("Brainstorm", cwd="/worktree")
    cmd = mock_run.call_args[0][0]
    assert cmd == ["claude", "Brainstorm"]
    assert mock_run.call_args[1].get("cwd") == "/worktree"


def test_launch_interactive_session_no_capture_output():
    with patch("devflow_sdk.core.ai.shutil.which", return_value="/usr/bin/claude"), \
         patch("devflow_sdk.core.ai.subprocess.run") as mock_run:
        launch_interactive_session("Brainstorm")
    assert "capture_output" not in mock_run.call_args[1]


def test_launch_interactive_session_does_not_launch_when_binary_not_found():
    with patch("devflow_sdk.core.ai.shutil.which", return_value=None), \
         patch("devflow_sdk.core.ai.subprocess.run") as mock_run:
        launch_interactive_session("Brainstorm")
    mock_run.assert_not_called()


def test_launch_interactive_session_uses_opencode_when_configured(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text('{"ai_provider": "opencode"}')
    monkeypatch.setattr("devflow_sdk.core.config.io.CONFIG_PATH", cfg)
    with patch("devflow_sdk.core.ai.shutil.which", return_value="/usr/bin/opencode"), \
         patch("devflow_sdk.core.ai.subprocess.run") as mock_run:
        launch_interactive_session("Brainstorm")
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "opencode"
