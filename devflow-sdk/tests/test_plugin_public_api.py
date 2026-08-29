"""Smoke test: every symbol in core.plugin.__all__ must be importable."""


def test_all_public_symbols_importable():
    from devflow_sdk.core.plugin import (
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
