import glob as _glob
import os
import sys

import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR_DIR = os.path.join(SCRIPT_DIR, "..", "vendor")
for _whl in sorted(_glob.glob(os.path.join(VENDOR_DIR, "*.whl"))):
    sys.path.insert(0, _whl)
sys.path.insert(0, SCRIPT_DIR)

from config import DirectoryRule, DraftPrConfig, resolve_plugin
from devflow_sdk.config import DevflowConfig, PluginConfig, load_tool_config


# ── DirectoryRule ─────────────────────────────────────────────────────────────

def test_directory_rule_fields():
    rule = DirectoryRule(paths=["frontend/", "ui/"], plugin="frontend-pr")
    assert rule.paths == ["frontend/", "ui/"]
    assert rule.plugin == "frontend-pr"


# ── DraftPrConfig defaults ────────────────────────────────────────────────────

def test_draft_pr_config_defaults():
    cfg = DraftPrConfig()
    assert cfg.plugin.default is None
    assert cfg.plugin.rules == []


# ── DraftPrConfig: raw dict deserialization ───────────────────────────────────

def test_draft_pr_config_hydrates_plugin_from_dict():
    raw_plugin = {
        "default": "default-pr",
        "rules": [
            {"paths": ["frontend/", "ui/"], "plugin": "frontend-pr"},
            {"paths": ["backend/"], "plugin": "backend-pr"},
        ]
    }
    cfg = DraftPrConfig(plugin=raw_plugin)
    assert cfg.plugin.default == "default-pr"
    assert len(cfg.plugin.rules) == 2
    assert isinstance(cfg.plugin.rules[0], DirectoryRule)


# ── DraftPrConfig: sorting ────────────────────────────────────────────────────

def test_draft_pr_config_sorts_rules_longest_path_first():
    raw_plugin = {
        "rules": [
            {"paths": ["a/"], "plugin": "short"},
            {"paths": ["a/very/long/path/"], "plugin": "long"},
            {"paths": ["a/medium/"], "plugin": "medium"},
        ]
    }
    cfg = DraftPrConfig(plugin=raw_plugin)
    plugins_in_order = [r.plugin for r in cfg.plugin.rules]
    assert plugins_in_order == ["long", "medium", "short"]


# ── DraftPrConfig: validate ───────────────────────────────────────────────────

def test_draft_pr_config_validate_passes_with_rules():
    cfg = DraftPrConfig(plugin={
        "rules": [{"paths": ["frontend/"], "plugin": "fp"}]
    })
    cfg.validate()  # should not raise


def test_draft_pr_config_validate_passes_with_default_only():
    cfg = DraftPrConfig(plugin={"default": "fallback"})
    cfg.validate()  # should not raise


def test_draft_pr_config_validate_fails_with_no_rules_and_no_default():
    cfg = DraftPrConfig()
    with pytest.raises(ValueError, match="at least one rule or a default"):
        cfg.validate()


def test_draft_pr_config_validate_fails_with_empty_paths_in_rule():
    cfg = DraftPrConfig(plugin={
        "rules": [{"paths": [], "plugin": "fp"}]
    })
    with pytest.raises(ValueError, match="at least one path"):
        cfg.validate()


# ── load_tool_config integration ──────────────────────────────────────────────

def test_load_tool_config_produces_valid_draft_pr_config():
    devflow_cfg = DevflowConfig(tools={
        "draft-pr": {
            "plugin": {
                "default": "default-pr",
                "rules": [{"paths": ["frontend/"], "plugin": "frontend-pr"}]
            }
        }
    })
    cfg = load_tool_config(devflow_cfg, "draft-pr", DraftPrConfig)
    assert isinstance(cfg, DraftPrConfig)
    assert cfg.plugin.default == "default-pr"
    assert cfg.plugin.rules[0].plugin == "frontend-pr"


def test_load_tool_config_calls_validate_on_draft_pr_config():
    devflow_cfg = DevflowConfig(tools={"draft-pr": {"plugin": {}}})
    with pytest.raises(ValueError, match="at least one rule or a default"):
        load_tool_config(devflow_cfg, "draft-pr", DraftPrConfig)


# ── resolve_plugin ────────────────────────────────────────────────────────────

def test_resolve_plugin_matches_prefix():
    # cwd uses a relative path so startswith("frontend/") works correctly
    cfg = DraftPrConfig(plugin={
        "rules": [{"paths": ["frontend/"], "plugin": "frontend-pr"}]
    })
    assert resolve_plugin(cfg, "frontend/my-app") == "frontend-pr"


def test_resolve_plugin_returns_default_when_no_match():
    cfg = DraftPrConfig(plugin={
        "default": "default-pr",
        "rules": [{"paths": ["frontend/"], "plugin": "frontend-pr"}]
    })
    assert resolve_plugin(cfg, "backend/service") == "default-pr"


def test_resolve_plugin_returns_none_when_no_match_and_no_default():
    cfg = DraftPrConfig(plugin={
        "rules": [{"paths": ["frontend/"], "plugin": "frontend-pr"}]
    })
    assert resolve_plugin(cfg, "backend/service") is None


def test_resolve_plugin_longer_path_wins_over_shorter():
    cfg = DraftPrConfig(plugin={
        "rules": [
            {"paths": ["frontend/"], "plugin": "generic-frontend"},
            {"paths": ["frontend/payments/"], "plugin": "payments"},
        ]
    })
    assert resolve_plugin(cfg, "frontend/payments/checkout") == "payments"


def test_resolve_plugin_matches_any_path_in_rule():
    cfg = DraftPrConfig(plugin={
        "rules": [{"paths": ["ui/", "frontend/"], "plugin": "frontend-pr"}]
    })
    assert resolve_plugin(cfg, "ui/components") == "frontend-pr"
    assert resolve_plugin(cfg, "frontend/app") == "frontend-pr"
