from __future__ import annotations

from collections.abc import Callable

from devflow_sdk.core.config.wizard.tools.draft_pr import DraftPrWizardStep
from devflow_sdk.core.config.wizard import WizardStep


def build_tool_steps(plugin_names: Callable[[], list[str]] | None = None) -> list[WizardStep]:
    return [DraftPrWizardStep(plugin_names)]


ALL_TOOL_STEPS: list[WizardStep] = build_tool_steps()
