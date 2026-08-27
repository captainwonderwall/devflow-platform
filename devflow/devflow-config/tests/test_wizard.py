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
