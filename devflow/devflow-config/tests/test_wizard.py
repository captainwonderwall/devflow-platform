import importlib.util
import os
import sys
from unittest.mock import call, patch

_HERE = os.path.dirname(__file__)
_TOOL_DIR = os.path.join(_HERE, "..")
_SDK_DIR = os.path.join(_HERE, "..", "..", "..", "devflow-sdk")
sys.path.insert(0, _SDK_DIR)

# Load devflow-config.py (hyphen in filename prevents normal import)
_spec = importlib.util.spec_from_file_location(
    "devflow_config", os.path.join(_TOOL_DIR, "devflow-config.py")
)
devflow_config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(devflow_config)

from devflow_sdk.config.wizard.global_steps import ModelsStep, ProviderStep
from devflow_sdk.config.wizard.tools import ALL_TOOL_STEPS
from devflow_sdk.config.wizard.tools.draft_pr import DraftPrWizardStep


# ── entry point ───────────────────────────────────────────────────────────────

def test_main_calls_run_wizard_with_correct_steps(capsys):
    from devflow_sdk.config.schema import DevflowConfig
    with patch.object(devflow_config, "run_wizard", return_value=DevflowConfig()) as mock_wizard:
        devflow_config.main()

    assert mock_wizard.call_count == 1
    steps = mock_wizard.call_args[0][0]
    assert isinstance(steps[0], ProviderStep)
    assert isinstance(steps[1], ModelsStep)
    assert len(steps) == 2 + len(ALL_TOOL_STEPS)


def test_main_prints_save_confirmation(capsys):
    from devflow_sdk.config.schema import DevflowConfig
    with patch.object(devflow_config, "run_wizard", return_value=DevflowConfig()):
        devflow_config.main()

    captured = capsys.readouterr()
    assert "~/.devflow/config.json" in captured.out


# ── ALL_TOOL_STEPS ─────────────────────────────────────────────────────────────

def test_all_tool_steps_contains_draft_pr_wizard_step():
    assert any(isinstance(s, DraftPrWizardStep) for s in ALL_TOOL_STEPS)


def test_all_tool_steps_is_not_empty():
    assert len(ALL_TOOL_STEPS) > 0


# ── backup + repair ────────────────────────────────────────────────────────────

def test_main_backs_up_invalid_config(tmp_path):
    import re
    config_path = tmp_path / "config.json"
    config_path.write_text('{"global": {"models": {"turbo": {"name": "x"}}}, "tools": {}}')

    with patch.object(devflow_config, "CONFIG_PATH", config_path), \
         patch.object(devflow_config, "run_wizard"):
        devflow_config.main()

    backups = [f for f in tmp_path.iterdir() if re.match(r"config\.\d{8}-\d{6}\.bak\.json", f.name)]
    assert len(backups) == 1


def test_main_does_not_back_up_valid_config(tmp_path):
    import re
    config_path = tmp_path / "config.json"
    config_path.write_text('{"global": {"models": {"fast": {"name": "haiku"}}}, "tools": {}}')

    with patch.object(devflow_config, "CONFIG_PATH", config_path), \
         patch.object(devflow_config, "run_wizard"):
        devflow_config.main()

    backups = [f for f in tmp_path.iterdir() if re.match(r"config\.\d{8}-\d{6}\.bak\.json", f.name)]
    assert len(backups) == 0


def test_main_repairs_config_before_wizard(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text('{"global": {"models": {"turbo": {"name": "x"}, "fast": {"name": "haiku"}}}, "tools": {}}')

    import json as _json
    with patch.object(devflow_config, "CONFIG_PATH", config_path), \
         patch.object(devflow_config, "run_wizard"):
        devflow_config.main()

    data = _json.loads(config_path.read_text())
    assert "fast" in data["global"]["models"]
    assert "turbo" not in data["global"]["models"]


def test_main_still_runs_wizard_after_repair(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text('{"global": {"models": {"turbo": {"name": "x"}}}, "tools": {}}')

    from devflow_sdk.config.schema import DevflowConfig
    with patch.object(devflow_config, "CONFIG_PATH", config_path), \
         patch.object(devflow_config, "run_wizard", return_value=DevflowConfig()) as mock_wiz:
        devflow_config.main()

    assert mock_wiz.call_count == 1


def test_main_copies_opencode_config_and_updates_both_shells(tmp_path):
    from devflow_sdk.config.schema import DevflowConfig, GlobalConfig

    home = tmp_path / "home"

    config = DevflowConfig(global_config=GlobalConfig(ai_provider="opencode"))
    with patch.object(devflow_config, "Path") as path_cls, \
        patch.object(devflow_config, "run_wizard", return_value=config):
        path_cls.home.return_value = home
        devflow_config.main()

    copied = home / ".devflow" / "opencode.json"
    assert copied.read_text() == devflow_config._STOCK_OPENCODE_CONFIG.read_text()
    expected = (
        "# >>> devflow opencode config >>>\n"
        'if [ -f "$HOME/.devflow/opencode.json" ]; then\n'
        '    export OPENCODE_CONFIG_CONTENT="$(< "$HOME/.devflow/opencode.json")"\n'
        "fi\n"
        "# <<< devflow opencode config <<<"
    )
    assert expected in (home / ".zshrc").read_text()
    assert expected in (home / ".bashrc").read_text()


def test_main_updates_existing_opencode_shell_block_idempotently(tmp_path):
    from devflow_sdk.config.schema import DevflowConfig, GlobalConfig

    home = tmp_path / "home"
    old_block = (
        "# >>> devflow opencode config >>>\n"
        "export OPENCODE_CONFIG_CONTENT=old\n"
        "# <<< devflow opencode config <<<"
    )
    home.mkdir()
    (home / ".zshrc").write_text(f"before\n{old_block}\nafter\n")

    config = DevflowConfig(global_config=GlobalConfig(ai_provider="opencode"))
    with patch.object(devflow_config, "Path") as path_cls, \
        patch.object(devflow_config, "run_wizard", return_value=config):
        path_cls.home.return_value = home
        devflow_config.main()

    shell = (home / ".zshrc").read_text()
    assert shell.count("# >>> devflow opencode config >>>") == 1
    assert "export OPENCODE_CONFIG_CONTENT=old" not in shell
    assert shell.startswith("before\n")
    assert shell.endswith("after\n")
