import importlib.util
import inspect
import os
import sys

from devflow_sdk.plugin_base import PluginBase
from devflow_sdk.prompts import select


def discover(plugin_dir: str, base_cls: type) -> list[PluginBase]:
    plugins = []
    if not os.path.isdir(plugin_dir):
        return plugins
    for fname in sorted(os.listdir(plugin_dir)):
        if not fname.endswith(".py") or fname.startswith("_"):
            continue
        path = os.path.join(plugin_dir, fname)
        try:
            spec = importlib.util.spec_from_file_location(fname[:-3], path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception as exc:
            print(
                f"Warning: plugin '{fname}' failed to load — it may be incompatible "
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
                    plugins.append(attr())
                except Exception:
                    print(
                        f"Warning: plugin '{fname}' failed to load — it may be incompatible "
                        "with this version of devflow. Check for an updated release.",
                        file=sys.stderr,
                    )
    return plugins


def select_plugin(
    plugin_dir: str,
    base_cls: type,
    configured_name: str | None = None,
) -> PluginBase | None:
    plugins = discover(plugin_dir, base_cls)
    if not plugins:
        return None

    plugin_names = [p.name or type(p).__name__ for p in plugins]

    if configured_name:
        if configured_name in plugin_names:
            return plugins[plugin_names.index(configured_name)]
        print(
            f"Warning: configured plugin '{configured_name}' not found. "
            f"Available: {', '.join(plugin_names)}",
            file=sys.stderr,
        )

    if len(plugins) == 1:
        return plugins[0]

    chosen = select("Select format", choices=plugin_names)
    return plugins[plugin_names.index(chosen)]
