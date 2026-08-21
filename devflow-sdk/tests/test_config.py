import dataclasses
import json
import sys
from pathlib import Path

import pytest

from devflow_sdk.config import (
    DevflowConfig,
    GlobalConfig,
    ModelConfig,
    PluginConfig,
    load_config,
    load_tool_config,
)


# ── Type shape ────────────────────────────────────────────────────────────────

def test_global_config_defaults():
    cfg = GlobalConfig()
    assert cfg.ai_provider == "claude"
    assert cfg.models == {}


def test_devflow_config_defaults():
    cfg = DevflowConfig()
    assert isinstance(cfg.global_config, GlobalConfig)
    assert cfg.tools == {}


def test_plugin_config_defaults():
    pc = PluginConfig()
    assert pc.default is None
    assert pc.rules == []


def test_plugin_config_holds_typed_rules():
    @dataclasses.dataclass
    class MyRule:
        key: str

    pc = PluginConfig(default="fallback", rules=[MyRule(key="a")])
    assert pc.rules[0].key == "a"
    assert pc.default == "fallback"


# ── load_config: new two-layer format ─────────────────────────────────────────

def test_load_config_new_format(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({
        "global": {
            "ai_provider": "opencode",
            "models": {
                "fast": {"name": "my-fast-model"},
            }
        },
        "tools": {
            "draft-pr": {"title_format": "feat: {title}"}
        }
    }))
    monkeypatch.setattr("devflow_sdk.config.CONFIG_PATH", cfg_file)

    result = load_config()
    assert result.global_config.ai_provider == "opencode"
    assert result.global_config.models["fast"].name == "my-fast-model"
    assert result.tools["draft-pr"]["title_format"] == "feat: {title}"


def test_load_config_missing_file_returns_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "devflow_sdk.config.CONFIG_PATH", tmp_path / "nonexistent.json"
    )
    result = load_config()
    assert result.global_config.ai_provider == "claude"
    assert result.tools == {}


def test_load_config_empty_tools(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"global": {"ai_provider": "claude"}}))
    monkeypatch.setattr("devflow_sdk.config.CONFIG_PATH", cfg_file)
    result = load_config()
    assert result.tools == {}


# ── load_config: legacy flat format ──────────────────────────────────────────

def test_load_config_legacy_flat_format_migrates(tmp_path, monkeypatch, capsys):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({
        "ai_provider": "opencode",
        "models": {"fast": {"name": "legacy-model"}}
    }))
    monkeypatch.setattr("devflow_sdk.config.CONFIG_PATH", cfg_file)

    result = load_config()
    assert result.global_config.ai_provider == "opencode"
    assert result.global_config.models["fast"].name == "legacy-model"
    assert result.tools == {}
    err = capsys.readouterr().err
    assert "outdated" in err


# ── load_config: validation errors ────────────────────────────────────────────

def test_load_config_invalid_json_raises(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text("{bad json")
    monkeypatch.setattr("devflow_sdk.config.CONFIG_PATH", cfg_file)
    with pytest.raises(ValueError, match="not valid JSON"):
        load_config()


def test_load_config_unknown_tier_raises(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({
        "global": {"models": {"turbo": {"name": "x"}}}
    }))
    monkeypatch.setattr("devflow_sdk.config.CONFIG_PATH", cfg_file)
    with pytest.raises(ValueError, match="unknown model tier 'turbo'"):
        load_config()


def test_load_config_missing_model_name_raises(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({
        "global": {"models": {"fast": {"pricing": None}}}
    }))
    monkeypatch.setattr("devflow_sdk.config.CONFIG_PATH", cfg_file)
    with pytest.raises(ValueError, match="missing required 'name' field"):
        load_config()


def test_load_config_incomplete_pricing_raises(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({
        "global": {"models": {"fast": {"name": "m", "pricing": {"input": 1.0}}}}
    }))
    monkeypatch.setattr("devflow_sdk.config.CONFIG_PATH", cfg_file)
    with pytest.raises(ValueError, match="pricing is missing required keys"):
        load_config()


# ── load_tool_config ──────────────────────────────────────────────────────────

def test_load_tool_config_returns_typed_instance():
    @dataclasses.dataclass
    class MyConfig:
        title: str = "default"

    cfg = DevflowConfig(tools={"my-tool": {"title": "hello"}})
    result = load_tool_config(cfg, "my-tool", MyConfig)
    assert isinstance(result, MyConfig)
    assert result.title == "hello"


def test_load_tool_config_missing_tool_returns_defaults_without_calling_validate():
    @dataclasses.dataclass
    class MyConfig:
        title: str = "default"

        def validate(self):
            raise ValueError("should not be called for unconfigured tools")

    cfg = DevflowConfig(tools={})
    result = load_tool_config(cfg, "missing-tool", MyConfig)
    assert result.title == "default"  # no exception means validate was not called


def test_load_tool_config_ignores_unknown_keys():
    @dataclasses.dataclass
    class MyConfig:
        title: str = "default"

    cfg = DevflowConfig(tools={"t": {"title": "hi", "unknown_key": "boom"}})
    result = load_tool_config(cfg, "t", MyConfig)
    assert result.title == "hi"


def test_load_tool_config_calls_validate_when_defined():
    @dataclasses.dataclass
    class StrictConfig:
        value: int = 0

        def validate(self):
            if self.value < 0:
                raise ValueError("value must be non-negative")

    cfg = DevflowConfig(tools={"t": {"value": -1}})
    with pytest.raises(ValueError, match="non-negative"):
        load_tool_config(cfg, "t", StrictConfig)


def test_load_tool_config_skips_validate_when_absent():
    @dataclasses.dataclass
    class SimpleConfig:
        value: int = 0

    cfg = DevflowConfig(tools={"t": {"value": 5}})
    result = load_tool_config(cfg, "t", SimpleConfig)
    assert result.value == 5
