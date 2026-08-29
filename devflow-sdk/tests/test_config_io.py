import json
import pytest
from pathlib import Path

from devflow_sdk.core.config import (
    DevflowConfig,
    GlobalConfig,
    ModelConfig,
    load_config,
    save_config,
    merge_config,
)
from devflow_sdk.core.config.io import repair_config


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


# ── repair_config ─────────────────────────────────────────────────────────────

def test_repair_config_removes_unknown_model_tier(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "global": {"models": {"fast": {"name": "haiku"}, "turbo": {"name": "gpt-x"}}},
        "tools": {},
    }))
    repair_config(path=config_path)
    data = json.loads(config_path.read_text())
    assert "fast" in data["global"]["models"]
    assert "turbo" not in data["global"]["models"]


def test_repair_config_removes_model_entry_missing_name(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "global": {"models": {"fast": {"pricing": {"input": 1, "output": 2, "cache_read": 0, "cache_write": 0}}}},
        "tools": {},
    }))
    repair_config(path=config_path)
    data = json.loads(config_path.read_text())
    assert "fast" not in data["global"]["models"]


def test_repair_config_drops_incomplete_pricing_keeps_model_name(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "global": {"models": {"capable": {"name": "sonnet", "pricing": {"input": 1}}}},
        "tools": {},
    }))
    repair_config(path=config_path)
    data = json.loads(config_path.read_text())
    assert data["global"]["models"]["capable"]["name"] == "sonnet"
    assert "pricing" not in data["global"]["models"]["capable"]


def test_repair_config_removes_invalid_tool_entry(tmp_path):
    from dataclasses import dataclass

    @dataclass
    class StrictConfig:
        value: str = ""

        def validate(self):
            if not self.value:
                raise ValueError("value required")

    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "global": {"models": {}},
        "tools": {"my-tool": {"value": ""}, "other-tool": {"x": 1}},
    }))
    repair_config(path=config_path, tool_registry={"my-tool": StrictConfig})
    data = json.loads(config_path.read_text())
    assert "my-tool" not in data["tools"]
    assert "other-tool" in data["tools"]


def test_repair_config_resets_invalid_json_to_empty(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("not valid json {{")
    repair_config(path=config_path)
    data = json.loads(config_path.read_text())
    assert data == {}


def test_repair_config_resets_non_object_root_to_empty(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps([1, 2, 3]))
    repair_config(path=config_path)
    data = json.loads(config_path.read_text())
    assert data == {}


def test_repair_config_preserves_valid_content(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "global": {
            "ai_provider": "claude",
            "models": {
                "fast": {"name": "haiku"},
                "capable": {"name": "sonnet", "pricing": {"input": 1, "output": 2, "cache_read": 0, "cache_write": 0}},
            },
        },
        "tools": {"draft-pr": {"plugin": {"default": "smoke"}}},
    }))
    repair_config(path=config_path)
    data = json.loads(config_path.read_text())
    assert data["global"]["models"]["fast"]["name"] == "haiku"
    assert data["global"]["models"]["capable"]["name"] == "sonnet"
    assert data["tools"]["draft-pr"]["plugin"]["default"] == "smoke"


def test_repair_config_nonexistent_file_creates_empty(tmp_path):
    config_path = tmp_path / "config.json"
    repair_config(path=config_path)
    data = json.loads(config_path.read_text())
    assert data == {}
