"""Smoke test: public API is accessible from the canonical path."""

_EXPECTED_NAMES = [
    "PluginBase",
    "PluginLoaderBase",
    "PluginLoader",
    "PluginEntry",
    "DraftPrPlugin",
    "select_plugin",
    "register",
    "unregister",
    "list_plugins",
    "discover",
]


def test_new_path_exports_all_public_symbols():
    from devflow_sdk.plugin import (
        PluginBase,
        PluginLoaderBase,
        PluginLoader,
        PluginEntry,
        DraftPrPlugin,
        select_plugin,
        register,
        unregister,
        list_plugins,
        discover,
    )
    assert PluginBase is not None
    assert DraftPrPlugin is not None
    assert select_plugin is not None


def test_new_path_all_matches_expected():
    import devflow_sdk.plugin as pkg
    for name in _EXPECTED_NAMES:
        assert name in pkg.__all__, f"{name!r} missing from devflow_sdk.plugin.__all__"
        assert getattr(pkg, name) is not None
