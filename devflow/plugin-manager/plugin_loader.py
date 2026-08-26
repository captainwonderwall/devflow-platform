from __future__ import annotations

from devflow_sdk.plugin.plugin_loader_impl import PluginLoader

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
