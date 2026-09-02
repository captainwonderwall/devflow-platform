"""Smoke test: public API accessible from both the new and deprecated paths."""
import warnings

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


def test_deprecated_path_reexports_same_symbols():
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        import devflow_sdk.core.plugin as shim
        import devflow_sdk.plugin as new_pkg
    for name in _EXPECTED_NAMES:
        assert getattr(shim, name) is getattr(new_pkg, name), \
            f"{name!r} identity mismatch between shim and new package"


def test_deprecated_path_emits_deprecation_warning():
    # Re-import in a fresh scope to ensure the warning fires
    import sys
    # Remove cached module so the warning triggers again
    for key in list(sys.modules):
        if "devflow_sdk.core.plugin" in key and key != "devflow_sdk.core":
            del sys.modules[key]

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        import devflow_sdk.core.plugin  # noqa: F401
        assert any(
            issubclass(warning.category, DeprecationWarning)
            and "deprecated" in str(warning.message)
            for warning in w
        ), "Expected DeprecationWarning from devflow_sdk.core.plugin import"
