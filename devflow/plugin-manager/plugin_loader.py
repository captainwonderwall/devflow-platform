from __future__ import annotations

import fcntl
import importlib.util
import inspect
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import TypeVar

from devflow_sdk.plugin_loader import PluginLoaderBase
from devflow_sdk.plugin_registry import PluginEntry
from devflow_sdk.prompts import select

REGISTRY_PATH = Path.home() / ".devflow" / "plugin-registry.json"
REGISTRY_VERSION = 1

T = TypeVar("T")


def _load_registry(registry_path: Path = REGISTRY_PATH) -> dict[str, PluginEntry]:
    if not registry_path.exists():
        return {}
    try:
        data = json.loads(registry_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"[devflow] Warning: plugin registry is unreadable: {e}", file=sys.stderr)
        return {}
    if not isinstance(data, dict) or data.get("version") != REGISTRY_VERSION:
        print("[devflow] Warning: plugin registry format is unrecognized.", file=sys.stderr)
        return {}
    return {
        name: PluginEntry(name=name, path=entry["path"], formula=entry.get("formula"))
        for name, entry in data.get("plugins", {}).items()
        if isinstance(entry, dict) and "path" in entry
    }


def _save_registry(plugins: dict[str, PluginEntry], registry_path: Path = REGISTRY_PATH) -> None:
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": REGISTRY_VERSION,
        "plugins": {
            name: {
                "path": e.path,
                **({"formula": e.formula} if e.formula else {}),
            }
            for name, e in plugins.items()
        },
    }
    fd, tmp_path = tempfile.mkstemp(dir=registry_path.parent, prefix=".registry-")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, indent=2)
            f.write("\n")
        os.rename(tmp_path, registry_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _atomic_update_registry(
    mutation_fn, registry_path: Path = REGISTRY_PATH
) -> None:
    """Apply a mutation to the registry atomically using file locking."""
    lock_path = registry_path.parent / ".registry.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with open(lock_path, "a") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            # Re-load under lock to get latest state
            plugins = _load_registry(registry_path)
            # Apply the mutation
            mutation_fn(plugins)
            # Save atomically
            _save_registry(plugins, registry_path)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)



class PluginLoader(PluginLoaderBase):

    def __init__(self, registry_path: Path = REGISTRY_PATH) -> None:
        self._registry_path = registry_path

    def register(self, name: str, path: str, formula: str | None = None) -> None:
        def mutate(plugins):
            plugins[name] = PluginEntry(name=name, path=path, formula=formula)

        _atomic_update_registry(mutate, self._registry_path)

    def unregister(self, name: str) -> None:
        def mutate(plugins):
            if name in plugins:
                del plugins[name]

        _atomic_update_registry(mutate, self._registry_path)

    def list_plugins(self) -> dict[str, PluginEntry]:
        return _load_registry(self._registry_path)

    def discover(self, base_cls: type[T]) -> dict[str, T]:
        stale: list[str] = []

        def _purge_stale(plugins: dict[str, PluginEntry]) -> None:
            for name in list(plugins):
                if not os.path.exists(plugins[name].path):
                    stale.append(name)
                    del plugins[name]

        _atomic_update_registry(_purge_stale, self._registry_path)
        for name in stale:
            logging.warning("[devflow] plugin '%s' not found on disk — purging stale registry entry.", name)

        found: dict[str, T] = {}
        for name, entry in _load_registry(self._registry_path).items():
            path = Path(entry.path)
            try:
                spec = importlib.util.spec_from_file_location(name, path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
            except Exception:
                print(
                    f"[devflow] Warning: plugin '{name}' failed to load — it may be incompatible "
                    "with this version of devflow. Check for an updated release.",
                    file=sys.stderr,
                )
                continue
            for attr in vars(mod).values():
                if (
                    isinstance(attr, type)
                    and issubclass(attr, base_cls)
                    and attr is not base_cls
                    and not inspect.isabstract(attr)
                ):
                    try:
                        found[name] = attr()
                    except Exception:
                        print(
                            f"[devflow] Warning: plugin '{name}' failed to instantiate — "
                            "it may be incompatible with this version of devflow. "
                            "Check for an updated release.",
                            file=sys.stderr,
                        )
                    break
        return found

    def select_plugin(self, base_cls: type[T], configured_name: str | None = None) -> T | None:
        plugins = self.discover(base_cls)
        if not plugins:
            return None
        if configured_name:
            if configured_name in plugins:
                return plugins[configured_name]
            print(
                f"[devflow] Warning: configured plugin '{configured_name}' not found. "
                f"Available: {', '.join(plugins.keys())}",
                file=sys.stderr,
            )
        if len(plugins) == 1:
            return next(iter(plugins.values()))
        chosen = select("Select plugin", choices=list(plugins.keys()))
        return plugins[chosen]


_loader = PluginLoader()
register = _loader.register
unregister = _loader.unregister
list_plugins = _loader.list_plugins
discover = _loader.discover
select_plugin = _loader.select_plugin


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(prog="devflow-plugin")
    sub = parser.add_subparsers(dest="cmd", required=True)

    reg_p = sub.add_parser("register", help="Register a plugin")
    reg_p.add_argument("name", help="Plugin name")
    reg_p.add_argument("path", help="Absolute path to the plugin .py file")
    reg_p.add_argument("--formula", default=None, help="Homebrew formula identifier (tap/name)")

    unreg_p = sub.add_parser("unregister", help="Unregister a plugin")
    unreg_p.add_argument("name", help="Plugin name to remove")

    sub.add_parser("list", help="List all registered plugins")

    args = parser.parse_args()
    loader = PluginLoader()

    if args.cmd == "register":
        loader.register(args.name, args.path, args.formula)
    elif args.cmd == "unregister":
        loader.unregister(args.name)
    elif args.cmd == "list":
        found = loader.list_plugins()
        if not found:
            print("No plugins registered.")
        else:
            for pname, entry in found.items():
                print(f"{pname}: {entry.path}")
