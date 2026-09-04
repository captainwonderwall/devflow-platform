from pathlib import Path

from devflow_sdk.plugin import DraftPrPlugin, PluginEntry
from devflow_sdk.plugin.plugin_path_loader import load_plugin


def write_plugin(path: Path, source: str) -> PluginEntry:
    path.write_text(source)
    return PluginEntry(name="test-plugin", path=str(path))


def test_load_plugin_returns_concrete_class_instance(tmp_path: Path) -> None:
    entry = write_plugin(
        tmp_path / "plugin.py",
        """
from devflow_sdk.plugin import DraftPrPlugin
class TestPlugin(DraftPrPlugin):
    name = 'Test'
    def get_questions(self, data): return []
    def build_prompt(self, data, user_inputs): return ''
    def build_body(self, ai_result, user_inputs): return ''
""",
    )

    result = load_plugin(entry, DraftPrPlugin)

    assert result.succeeded
    assert result.plugin.__class__.__name__ == "TestPlugin"


def test_load_plugin_reports_import_failure(tmp_path: Path) -> None:
    entry = write_plugin(tmp_path / "plugin.py", "raise RuntimeError('broken')")

    result = load_plugin(entry, DraftPrPlugin)

    assert not result.succeeded
    assert result.failure is not None
    assert result.failure.phase == "load"


def test_load_plugin_reports_missing_concrete_class(tmp_path: Path) -> None:
    entry = write_plugin(tmp_path / "plugin.py", "VALUE = 1")

    result = load_plugin(entry, DraftPrPlugin)

    assert not result.succeeded
    assert result.failure is not None
    assert result.failure.phase == "class-selection"


def test_load_plugin_rejects_ambiguous_module(tmp_path: Path) -> None:
    entry = write_plugin(
        tmp_path / "plugin.py",
        """
from devflow_sdk.plugin import DraftPrPlugin
class First(DraftPrPlugin):
    name = 'First'
    def get_questions(self, data): return []
    def build_prompt(self, data, user_inputs): return ''
    def build_body(self, ai_result, user_inputs): return ''
class Second(DraftPrPlugin):
    name = 'Second'
    def get_questions(self, data): return []
    def build_prompt(self, data, user_inputs): return ''
    def build_body(self, ai_result, user_inputs): return ''
""",
    )

    result = load_plugin(entry, DraftPrPlugin)

    assert not result.succeeded
    assert result.failure is not None
    assert result.failure.phase == "class-selection"
