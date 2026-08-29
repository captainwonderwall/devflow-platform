import dataclasses
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from devflow_sdk.core.config import DevflowConfig, GlobalConfig
from devflow_sdk.core.config.wizard import WizardStep, run_wizard


class _ProviderSwitchStep(WizardStep):
    section = "Test Section"

    def run(self, current: DevflowConfig) -> DevflowConfig:
        return dataclasses.replace(
            current,
            global_config=dataclasses.replace(current.global_config, ai_provider="opencode"),
        )


def test_wizard_step_is_abstract():
    import inspect
    assert inspect.isabstract(WizardStep)


def test_wizard_step_section_required():
    with pytest.raises(TypeError):
        WizardStep()


def test_run_wizard_calls_steps_in_order(tmp_path):
    order = []

    class StepA(WizardStep):
        section = "A"
        def run(self, current):
            order.append("A")
            return current

    class StepB(WizardStep):
        section = "B"
        def run(self, current):
            order.append("B")
            return current

    config_path = tmp_path / "config.json"
    run_wizard([StepA(), StepB()], path=config_path)
    assert order == ["A", "B"]


def test_run_wizard_saves_final_config(tmp_path):
    config_path = tmp_path / "config.json"
    run_wizard([_ProviderSwitchStep()], path=config_path)
    from devflow_sdk.core.config import load_config
    result = load_config(path=config_path)
    assert result.global_config.ai_provider == "opencode"


def test_run_wizard_loads_existing_config(tmp_path):
    config_path = tmp_path / "config.json"
    from devflow_sdk.core.config import save_config
    save_config(
        DevflowConfig(global_config=GlobalConfig(ai_provider="opencode")),
        path=config_path,
    )

    seen = []

    class InspectStep(WizardStep):
        section = "Inspect"
        def run(self, current):
            seen.append(current.global_config.ai_provider)
            return current

    run_wizard([InspectStep()], path=config_path)
    assert seen[0] == "opencode"


def test_run_wizard_step_return_propagates_to_next(tmp_path):
    config_path = tmp_path / "config.json"

    class SetProvider(WizardStep):
        section = "Provider"
        def run(self, current):
            return dataclasses.replace(
                current,
                global_config=dataclasses.replace(current.global_config, ai_provider="opencode"),
            )

    class AssertProvider(WizardStep):
        section = "Assert"
        def run(self, current):
            assert current.global_config.ai_provider == "opencode"
            return current

    run_wizard([SetProvider(), AssertProvider()], path=config_path)


def test_wizard_step_tool_name_defaults_to_none():
    class MinimalStep(WizardStep):
        section = "X"
        def run(self, current):
            return current

    assert MinimalStep.tool_name is None


def test_wizard_step_schema_cls_defaults_to_none():
    class MinimalStep(WizardStep):
        section = "X"
        def run(self, current):
            return current

    assert MinimalStep.schema_cls is None


def test_draft_pr_wizard_step_tool_name():
    from devflow_sdk.core.config.wizard.tools.draft_pr import DraftPrWizardStep
    assert DraftPrWizardStep.tool_name == "draft-pr"


def test_draft_pr_wizard_step_schema_cls():
    from devflow_sdk.core.config.wizard.tools.draft_pr import DraftPrWizardStep, DraftPrConfig
    assert DraftPrWizardStep.schema_cls is DraftPrConfig
