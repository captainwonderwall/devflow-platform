#!/usr/bin/env python3
import shutil
from datetime import datetime

from devflow_sdk.config.io import CONFIG_PATH, load_config, load_tool_config, repair_config
from devflow_sdk.config.wizard import run_wizard
from devflow_sdk.config.wizard.global_steps import ModelsStep, ProviderStep
from devflow_sdk.config.wizard.tools import ALL_TOOL_STEPS


def _config_is_valid(tool_registry: dict) -> bool:
    try:
        config = load_config(path=CONFIG_PATH)
        for tool_name, schema_cls in tool_registry.items():
            load_tool_config(config, tool_name, schema_cls)
        return True
    except Exception:
        return False


def _backup_config() -> None:
    if not CONFIG_PATH.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = CONFIG_PATH.parent / f"config.{stamp}.bak.json"
    shutil.copy2(CONFIG_PATH, dest)


def main():
    steps = [ProviderStep(), ModelsStep()] + ALL_TOOL_STEPS
    tool_registry = {s.tool_name: s.schema_cls for s in steps if s.tool_name}

    if not _config_is_valid(tool_registry):
        _backup_config()
        repair_config(path=CONFIG_PATH, tool_registry=tool_registry)

    run_wizard(steps)
    print("\nConfig saved to ~/.devflow/config.json")


if __name__ == "__main__":
    main()
