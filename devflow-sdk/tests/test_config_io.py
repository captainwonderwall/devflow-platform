import json
import pytest
from pathlib import Path

from devflow_sdk.config import (
    DevflowConfig,
    GlobalConfig,
    ModelConfig,
    load_config,
    save_config,
    merge_config,
)


def test_save_config_creates_valid_json(tmp_path):
    config_path = tmp_path / "config.json"
    config = DevflowConfig(
        global_config=GlobalConfig(
            ai_provider="opencode",
            models={"fast": ModelConfig(name="my-fast")},
        )
    )
    save_config(config, path=config_path)
    data = json.loads(config_path.read_text())
    assert data["global"]["ai_provider"] == "opencode"
    assert data["global"]["models"]["fast"]["name"] == "my-fast"


def test_save_config_roundtrip(tmp_path):
    config_path = tmp_path / "config.json"
    original = DevflowConfig(
        global_config=GlobalConfig(
            ai_provider="claude",
            models={
                "fast": ModelConfig(
                    name="claude-haiku-4-5-20251001",
                    pricing={"input": 0.8, "output": 4.0, "cache_read": 0.08, "cache_write": 1.0},
                ),
                "capable": ModelConfig(name="claude-sonnet-4-6"),
            },
        ),
        tools={"draft-pr": {"plugin": {"default": "smoke-check"}}},
    )
    save_config(original, path=config_path)
    loaded = load_config(path=config_path)
    assert loaded.global_config.ai_provider == "claude"
    assert loaded.global_config.models["fast"].name == "claude-haiku-4-5-20251001"
    assert loaded.tools["draft-pr"]["plugin"]["default"] == "smoke-check"


def test_save_config_leaves_no_temp_files(tmp_path):
    config_path = tmp_path / "config.json"
    save_config(DevflowConfig(), path=config_path)
    leftovers = [f for f in tmp_path.iterdir() if f.name.startswith(".config-")]
    assert leftovers == []


def test_merge_config_overlay_ai_provider_wins():
    base = DevflowConfig(global_config=GlobalConfig(ai_provider="claude"))
    overlay = DevflowConfig(global_config=GlobalConfig(ai_provider="opencode"))
    result = merge_config(base, overlay)
    assert result.global_config.ai_provider == "opencode"


def test_merge_config_models_merged_by_key():
    fast = ModelConfig(name="haiku")
    capable = ModelConfig(name="sonnet")
    base = DevflowConfig(global_config=GlobalConfig(models={"fast": fast}))
    overlay = DevflowConfig(global_config=GlobalConfig(models={"capable": capable}))
    result = merge_config(base, overlay)
    assert "fast" in result.global_config.models
    assert "capable" in result.global_config.models


def test_merge_config_tools_merged_by_key():
    base = DevflowConfig(tools={"draft-pr": {"x": 1}})
    overlay = DevflowConfig(tools={"squash-commits": {"y": 2}})
    result = merge_config(base, overlay)
    assert "draft-pr" in result.tools
    assert "squash-commits" in result.tools


def test_merge_config_overlay_tool_wins():
    base = DevflowConfig(tools={"draft-pr": {"plugin": {"default": "old"}}})
    overlay = DevflowConfig(tools={"draft-pr": {"plugin": {"default": "new"}}})
    result = merge_config(base, overlay)
    assert result.tools["draft-pr"]["plugin"]["default"] == "new"


def test_save_config_preserves_unknown_root_keys(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "global": {"ai_provider": "claude", "models": {}},
        "tools": {},
        "experimental": {"feature_x": True},
    }))
    config = load_config(path=config_path)
    save_config(config, path=config_path)
    data = json.loads(config_path.read_text())
    assert data["experimental"] == {"feature_x": True}


def test_save_config_preserves_unknown_global_keys(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "global": {"ai_provider": "claude", "models": {}, "telemetry": False},
        "tools": {},
    }))
    config = load_config(path=config_path)
    save_config(config, path=config_path)
    data = json.loads(config_path.read_text())
    assert data["global"]["telemetry"] is False
