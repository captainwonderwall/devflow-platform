import importlib.util
import inspect
import os

from devflow_sdk.plugin_base import PluginBase


def discover(plugin_dir: str) -> list:
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
        except Exception:
            continue
        for attr in vars(mod).values():
            if (
                isinstance(attr, type)
                and issubclass(attr, PluginBase)
                and attr is not PluginBase
                and not inspect.isabstract(attr)
            ):
                try:
                    plugins.append(attr())
                except Exception:
                    continue
    return plugins
