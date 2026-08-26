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
