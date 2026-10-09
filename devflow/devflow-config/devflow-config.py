#!/usr/bin/env python3
import json
import shutil
from datetime import datetime
from pathlib import Path

from devflow_sdk.core.config.io import CONFIG_PATH, load_config, load_tool_config, repair_config
from devflow_sdk.core.config.wizard import run_wizard
from devflow_sdk.core.config.wizard.global_steps import ModelsStep, ProviderStep
from devflow_sdk.core.config.wizard.tools import build_tool_steps
from devflow_sdk.core.ui import error, success
from devflow_sdk.plugin import PluginLoader


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
        error(f"Warning: stock OpenCode config not found at {_STOCK_OPENCODE_CONFIG}; skipping OpenCode integration.")
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


_STOCK_CLAUDE_SETTINGS = Path(__file__).with_name("claude-settings.json")
_CLAUDE_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"


def _install_claude_config() -> None:
    """Merge devflow's Claude Code permissions into ~/.claude/settings.json."""
    if not _STOCK_CLAUDE_SETTINGS.exists():
        error(f"Warning: stock Claude settings not found at {_STOCK_CLAUDE_SETTINGS}; skipping.")
        return

    stock = json.loads(_STOCK_CLAUDE_SETTINGS.read_text())
    new_allow: list[str] = stock.get("permissions", {}).get("allow", [])
    new_unix_sockets: list[str] = [
        str(Path(s).expanduser())
        for s in stock.get("sandbox", {}).get("network", {}).get("allowUnixSockets", [])
    ]
    new_excluded_commands: list[str] = stock.get("sandbox", {}).get("excludedCommands", [])

    existing: dict = {}
    if _CLAUDE_SETTINGS_PATH.exists():
        try:
            existing = json.loads(_CLAUDE_SETTINGS_PATH.read_text())
        except Exception:
            error(
                f"Error: {_CLAUDE_SETTINGS_PATH} exists but could not be parsed as JSON.\n"
                f"Fix or remove it manually, then re-run devflow-config."
            )
            return

    if not isinstance(existing, dict):
        existing = {}

    permissions = existing.setdefault("permissions", {})
    if not isinstance(permissions, dict):
        existing["permissions"] = {}
        permissions = existing["permissions"]
    allow = permissions.get("allow", [])
    if not isinstance(allow, list):
        allow = []
    for entry in new_allow:
        if entry not in allow:
            allow.append(entry)
    permissions["allow"] = allow

    if new_unix_sockets:
        sandbox = existing.setdefault("sandbox", {})
        if not isinstance(sandbox, dict):
            existing["sandbox"] = {}
            sandbox = existing["sandbox"]
        network = sandbox.setdefault("network", {})
        if not isinstance(network, dict):
            sandbox["network"] = {}
            network = sandbox["network"]
        unix_sockets = network.get("allowUnixSockets", [])
        if not isinstance(unix_sockets, list):
            unix_sockets = []
        for entry in new_unix_sockets:
            if entry not in unix_sockets:
                unix_sockets.append(entry)
        network["allowUnixSockets"] = unix_sockets

    if new_excluded_commands:
        sandbox = existing.setdefault("sandbox", {})
        if not isinstance(sandbox, dict):
            existing["sandbox"] = {}
            sandbox = existing["sandbox"]
        excluded = sandbox.get("excludedCommands", [])
        if not isinstance(excluded, list):
            excluded = []
        for entry in new_excluded_commands:
            if entry not in excluded:
                excluded.append(entry)
        sandbox["excludedCommands"] = excluded

    _CLAUDE_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CLAUDE_SETTINGS_PATH.write_text(json.dumps(existing, indent=2) + "\n")
    success(f"Claude Code settings updated: {_CLAUDE_SETTINGS_PATH}")


def main():
    def _plugin_names() -> list[str]:
        try:
            return sorted(PluginLoader().list_plugins())
        except Exception as e:
            error(f"Warning: could not read plugin registry: {e}")
            return []

    steps = [ProviderStep(), ModelsStep()] + build_tool_steps(_plugin_names)
    tool_registry = {s.tool_name: s.schema_cls for s in steps if s.tool_name}

    if not _config_is_valid(tool_registry):
        _backup_config()
        repair_config(path=CONFIG_PATH, tool_registry=tool_registry)

    config = run_wizard(steps)
    if config.global_config.ai_provider == "opencode":
        _install_opencode_config()
    elif config.global_config.ai_provider == "claude":
        _install_claude_config()
    success("Config saved to ~/.devflow/config.json")


if __name__ == "__main__":
    main()
