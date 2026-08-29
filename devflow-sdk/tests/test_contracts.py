import pytest
from devflow_sdk.core.plugin.contracts import DraftPrPlugin
from devflow_sdk.core.plugin import PluginBase


def test_draft_pr_plugin_is_subclass_of_plugin_base():
    assert issubclass(DraftPrPlugin, PluginBase)


def test_draft_pr_plugin_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        DraftPrPlugin()


def test_incomplete_subclass_missing_build_body_cannot_be_instantiated():
    class Incomplete(DraftPrPlugin):
        name = "test"
        def get_questions(self, data): return []
        def build_prompt(self, data, user_inputs): return ""
    with pytest.raises(TypeError):
        Incomplete()


def test_complete_subclass_instantiates_and_delegates():
    class Complete(DraftPrPlugin):
        name = "Complete"
        def get_questions(self, data): return [{"id": "q1", "text": "Who?"}]
        def build_prompt(self, data, user_inputs): return "my prompt"
        def build_body(self, ai_result, user_inputs): return "# Body"

    plugin = Complete()
    assert plugin.name == "Complete"
    assert plugin.get_questions({}) == [{"id": "q1", "text": "Who?"}]
    assert plugin.build_prompt({}, {}) == "my prompt"
    assert plugin.build_body({}, {}) == "# Body"


def test_plugin_name_defaults_to_empty_string():
    class NoName(DraftPrPlugin):
        def get_questions(self, data): return []
        def build_prompt(self, data, user_inputs): return ""
        def build_body(self, ai_result, user_inputs): return ""
    assert NoName.name == ""
