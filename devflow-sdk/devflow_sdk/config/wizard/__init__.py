from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from devflow_sdk.config.io import load_config, save_config
from devflow_sdk.config.schema import DevflowConfig


class WizardStep(ABC):
    section: str
    tool_name: str | None = None
    schema_cls: type | None = None

    @abstractmethod
    def run(self, current: DevflowConfig) -> DevflowConfig:
        ...


def run_wizard(steps: list[WizardStep], path: Path | None = None) -> DevflowConfig:
    config = load_config(path=path)
    for step in steps:
        print(f"\n=== {step.section} ===")
        config = step.run(config)
    save_config(config, path=path)
    return config
