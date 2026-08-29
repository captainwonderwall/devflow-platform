import dataclasses
import pytest
from unittest.mock import MagicMock, patch

from devflow_sdk.core.config import DevflowConfig, GlobalConfig
from devflow_sdk.core.config.wizard.tools.draft_pr import (
    DraftPrConfig,
    DraftPrWizardStep,
    DirectoryRule,
    resolve_plugin,
)
from devflow_sdk.core.plugin import PluginEntry


def _make_config(draft_pr_tools=None):
    tools = {}
    if draft_pr_tools is not None:
        tools["draft-pr"] = draft_pr_tools
    return DevflowConfig(global_config=GlobalConfig(), tools=tools)


def _make_entry(name):
    return PluginEntry(name=name, path=f"/path/{name}.py", formula=None)


class TestDraftPrConfig:
    def test_defaults(self):
        cfg = DraftPrConfig()
        assert cfg.plugin.default is None
        assert cfg.plugin.rules == []

    def test_post_init_converts_dict(self):
        raw = {
            "plugin": {
                "default": "smoke-check",
                "rules": [{"paths": ["/src"], "plugin": "other"}],
            }
        }
        from devflow_sdk.core.config import load_tool_config, DevflowConfig, GlobalConfig
        config = DevflowConfig(global_config=GlobalConfig(), tools={"draft-pr": raw})
        draft_cfg = load_tool_config(config, "draft-pr", DraftPrConfig)
        assert draft_cfg.plugin.default == "smoke-check"
        assert draft_cfg.plugin.rules[0].paths == ["/src"]

    def test_validate_raises_when_no_default_and_no_rules(self):
        cfg = DraftPrConfig()
        with pytest.raises(ValueError, match="plugin config must have"):
            cfg.validate()

    def test_validate_passes_with_default(self):
        from devflow_sdk.core.config.schema import PluginConfig
        cfg = DraftPrConfig(plugin=PluginConfig(default="smoke-check"))
        cfg.validate()  # should not raise

    def test_rules_sorted_by_path_length_descending(self):
        from devflow_sdk.core.config.schema import PluginConfig
        rules = [
            DirectoryRule(paths=["/a"], plugin="short"),
            DirectoryRule(paths=["/a/b/c/d"], plugin="longest"),
            DirectoryRule(paths=["/a/b"], plugin="medium"),
        ]
        cfg = DraftPrConfig(plugin=PluginConfig(default=None, rules=rules))
        assert cfg.plugin.rules[0].plugin == "longest"
        assert cfg.plugin.rules[1].plugin == "medium"
        assert cfg.plugin.rules[2].plugin == "short"


class TestResolvePlugin:
    def test_matches_first_rule_by_path_prefix(self):
        from devflow_sdk.core.config.schema import PluginConfig
        rules = [DirectoryRule(paths=["/Users/foo/projects"], plugin="proj-plugin")]
        cfg = DraftPrConfig(plugin=PluginConfig(default="default-plugin", rules=rules))
        assert resolve_plugin(cfg, "/Users/foo/projects/myrepo") == "proj-plugin"

    def test_falls_back_to_default(self):
        from devflow_sdk.core.config.schema import PluginConfig
        cfg = DraftPrConfig(plugin=PluginConfig(default="fallback"))
        assert resolve_plugin(cfg, "/unmatched/path") == "fallback"

    def test_does_not_match_path_prefix_sibling(self):
        from devflow_sdk.core.config.schema import PluginConfig
        rules = [DirectoryRule(paths=["/foo/proj"], plugin="proj-plugin")]
        cfg = DraftPrConfig(plugin=PluginConfig(default="fallback", rules=rules))
        assert resolve_plugin(cfg, "/foo/projectX") == "fallback"

    def test_matches_exact_path(self):
        from devflow_sdk.core.config.schema import PluginConfig
        rules = [DirectoryRule(paths=["/foo/proj"], plugin="proj-plugin")]
        cfg = DraftPrConfig(plugin=PluginConfig(default="fallback", rules=rules))
        assert resolve_plugin(cfg, "/foo/proj") == "proj-plugin"


class TestDraftPrWizardStep:
    def test_section_label(self):
        assert DraftPrWizardStep().section == "draft-pr: Plugin Routing"

    def test_skips_when_no_plugins_registered(self, capsys):
        step = DraftPrWizardStep()
        current = _make_config()
        with patch(
            "devflow_sdk.core.config.wizard.tools.draft_pr.PluginLoader.list_plugins",
            return_value={},
        ):
            result = step.run(current)
        assert result == current
        captured = capsys.readouterr()
        assert "No plugins" in captured.out

    def test_sets_default_plugin(self):
        step = DraftPrWizardStep()
        current = _make_config()
        plugins = {"smoke-check": _make_entry("smoke-check")}
        with (
            patch("devflow_sdk.core.config.wizard.tools.draft_pr.PluginLoader.list_plugins", return_value=plugins),
            patch("devflow_sdk.core.config.wizard.tools.draft_pr.select", return_value="smoke-check"),
            patch("devflow_sdk.core.config.wizard.tools.draft_pr.checkbox", return_value=[]),
            patch("devflow_sdk.core.config.wizard.tools.draft_pr.confirm", return_value=False),
        ):
            result = step.run(current)
        assert result.tools["draft-pr"]["plugin"]["default"] == "smoke-check"

    def test_existing_rules_kept_when_all_selected(self):
        step = DraftPrWizardStep()
        existing_tools = {
            "plugin": {
                "default": "smoke-check",
                "rules": [{"paths": ["/src"], "plugin": "other-plugin"}],
            }
        }
        current = _make_config(draft_pr_tools=existing_tools)
        plugins = {
            "smoke-check": _make_entry("smoke-check"),
            "other-plugin": _make_entry("other-plugin"),
        }
        rule = DirectoryRule(paths=["/src"], plugin="other-plugin")
        with (
            patch("devflow_sdk.core.config.wizard.tools.draft_pr.PluginLoader.list_plugins", return_value=plugins),
            patch("devflow_sdk.core.config.wizard.tools.draft_pr.select", return_value="smoke-check"),
            patch("devflow_sdk.core.config.wizard.tools.draft_pr.checkbox", return_value=[rule]),
            patch("devflow_sdk.core.config.wizard.tools.draft_pr.confirm", return_value=False),
        ):
            result = step.run(current)
        rules = result.tools["draft-pr"]["plugin"]["rules"]
        assert any(r["paths"] == ["/src"] for r in rules)

    def test_cancel_on_rules_prompt_returns_config_unchanged(self):
        """Ctrl+C on the 'which rules to keep' prompt should leave config unchanged."""
        step = DraftPrWizardStep()
        existing_tools = {
            "plugin": {
                "default": "smoke-check",
                "rules": [{"paths": ["/src"], "plugin": "other-plugin"}],
            }
        }
        current = _make_config(draft_pr_tools=existing_tools)
        plugins = {
            "smoke-check": _make_entry("smoke-check"),
            "other-plugin": _make_entry("other-plugin"),
        }
        with (
            patch("devflow_sdk.core.config.wizard.tools.draft_pr.PluginLoader.list_plugins", return_value=plugins),
            patch("devflow_sdk.core.config.wizard.tools.draft_pr.select", return_value="smoke-check"),
            # None simulates Ctrl+C on the checkbox prompt
            patch("devflow_sdk.core.config.wizard.tools.draft_pr.checkbox", return_value=None),
        ):
            result = step.run(current)
        assert result == current

    def test_new_rule_added(self):
        step = DraftPrWizardStep()
        current = _make_config()
        plugins = {"smoke-check": _make_entry("smoke-check")}
        with (
            patch("devflow_sdk.core.config.wizard.tools.draft_pr.PluginLoader.list_plugins", return_value=plugins),
            patch("devflow_sdk.core.config.wizard.tools.draft_pr.select", return_value="smoke-check"),
            patch("devflow_sdk.core.config.wizard.tools.draft_pr.checkbox", return_value=[]),
            patch("devflow_sdk.core.config.wizard.tools.draft_pr.confirm", side_effect=[True, False]),
            patch("devflow_sdk.core.config.wizard.tools.draft_pr.text", return_value="/work/myproject"),
        ):
            result = step.run(current)
        rules = result.tools["draft-pr"]["plugin"]["rules"]
        assert any("/work/myproject" in r["paths"] for r in rules)
