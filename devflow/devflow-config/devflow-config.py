#!/usr/bin/env python3
import shutil
from datetime import datetime
from pathlib import Path

from devflow_sdk.core.config.io import CONFIG_PATH, load_config, load_tool_config, repair_config
from devflow_sdk.core.config.wizard import run_wizard
from devflow_sdk.core.config.wizard.global_steps import ModelsStep, ProviderStep
from devflow_sdk.core.config.wizard.tools import ALL_TOOL_STEPS


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


_OPENCODE_SHELL_SENTINEL = "# >>> devflow opencode config >>>"
_OPENCODE_SHELL_END = "# <<< devflow opencode config <<<"
_STOCK_OPENCODE_CONFIG = Path(__file__).with_name("opencode.json")


def _install_opencode_config() -> None:
    """Copy OpenCode's config and load it as the final shell-level override."""
    home = Path.home()
    target = home / ".devflow" / "opencode.json"
    if not _STOCK_OPENCODE_CONFIG.exists():
        print(f"\nWarning: stock OpenCode config not found at {_STOCK_OPENCODE_CONFIG}; skipping OpenCode integration.")
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_STOCK_OPENCODE_CONFIG, target)

    shell_block = (
        f"{_OPENCODE_SHELL_SENTINEL}\n"
        'if [ -f "$HOME/.devflow/opencode.json" ]; then\n'
        '    export OPENCODE_CONFIG_CONTENT="$(< "$HOME/.devflow/opencode.json")"\n'
        "fi\n"
        f"{_OPENCODE_SHELL_END}"
    )
    for rc_path in (home / ".zshrc", home / ".bashrc"):
        content = rc_path.read_text() if rc_path.exists() else ""
        if _OPENCODE_SHELL_SENTINEL in content:
            start = content.index(_OPENCODE_SHELL_SENTINEL)
            end_marker = content.find(_OPENCODE_SHELL_END, start)
            if end_marker >= 0:
                end = end_marker + len(_OPENCODE_SHELL_END)
                content = content[:start] + shell_block + content[end:]
            else:
                content = content[:start] + shell_block
        else:
            separator = "" if not content or content.endswith("\n") else "\n"
            content += f"{separator}\n{shell_block}\n"
        rc_path.write_text(content)


def main():
    steps = [ProviderStep(), ModelsStep()] + ALL_TOOL_STEPS
    tool_registry = {s.tool_name: s.schema_cls for s in steps if s.tool_name}

    if not _config_is_valid(tool_registry):
        _backup_config()
        repair_config(path=CONFIG_PATH, tool_registry=tool_registry)

    config = run_wizard(steps)
    if config.global_config.ai_provider == "opencode":
        _install_opencode_config()
    print("\nConfig saved to ~/.devflow/config.json")


if __name__ == "__main__":
    main()
