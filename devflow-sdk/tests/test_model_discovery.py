import json
from unittest.mock import patch

from devflow_sdk.core.config.wizard.tools.model_discovery import fetch_catalog, _CATALOG_PATH


_SAMPLE_PAYLOAD = {
    "anthropic": {
        "models": {
            "claude-sonnet-4-6": {
                "name": "Claude Sonnet 4.6",
                "cost": {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_write": 3.75},
            },
            "claude-haiku-4-5": {
                "name": "Claude Haiku 4.5",
                "cost": {"input": 1.0, "output": 5.0, "cache_read": 0.1, "cache_write": 1.25},
            },
        }
    },
    "github-copilot": {
        "models": {
            "claude-sonnet-4.6": {
                "name": "Claude Sonnet 4.6",
                "cost": {"input": 3.0, "output": 15.0, "cache_read": 0.3},
            },
        }
    },
}


class TestFetchCatalog:
    def test_returns_models_dict_for_known_key(self, tmp_path):
        catalog_file = tmp_path / "models_catalog.json"
        catalog_file.write_text(json.dumps(_SAMPLE_PAYLOAD))
        with patch("devflow_sdk.core.config.wizard.tools.model_discovery._CATALOG_PATH", catalog_file):
            result = fetch_catalog("anthropic")
        assert "claude-sonnet-4-6" in result
        assert result["claude-sonnet-4-6"]["name"] == "Claude Sonnet 4.6"

    def test_returns_none_when_file_missing(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        with patch("devflow_sdk.core.config.wizard.tools.model_discovery._CATALOG_PATH", missing):
            result = fetch_catalog("anthropic")
        assert result is None

    def test_returns_none_on_bad_json(self, tmp_path):
        catalog_file = tmp_path / "models_catalog.json"
        catalog_file.write_text("not json {")
        with patch("devflow_sdk.core.config.wizard.tools.model_discovery._CATALOG_PATH", catalog_file):
            result = fetch_catalog("anthropic")
        assert result is None

    def test_returns_none_for_missing_provider_key(self, tmp_path):
        catalog_file = tmp_path / "models_catalog.json"
        catalog_file.write_text(json.dumps({"other": {}}))
        with patch("devflow_sdk.core.config.wizard.tools.model_discovery._CATALOG_PATH", catalog_file):
            result = fetch_catalog("anthropic")
        assert result is None


from devflow_sdk.core.config.wizard.tools.model_discovery import list_models, OTHER_SENTINEL, lookup_pricing
from devflow_sdk.core.ai.providers.claude_provider import ClaudeProvider
from devflow_sdk.core.ai.providers.opencode_provider import OpenCodeProvider


class TestListModels:
    def test_uses_catalog_when_available(self):
        provider = ClaudeProvider()
        catalog = _SAMPLE_PAYLOAD["anthropic"]["models"]
        result = list_models(provider, catalog)
        model_ids = [mid for mid, _ in result]
        assert "claude-sonnet-4-6" in model_ids
        assert "claude-haiku-4-5" in model_ids

    def test_last_entry_is_other_sentinel(self):
        provider = ClaudeProvider()
        catalog = _SAMPLE_PAYLOAD["anthropic"]["models"]
        result = list_models(provider, catalog)
        assert result[-1] == (OTHER_SENTINEL, "Other (type manually)")

    def test_opencode_prefix_applied_to_catalog_ids(self):
        provider = OpenCodeProvider()
        catalog = _SAMPLE_PAYLOAD["github-copilot"]["models"]
        result = list_models(provider, catalog)
        model_ids = [mid for mid, _ in result]
        assert "github-copilot/claude-sonnet-4.6" in model_ids

    def test_falls_back_to_provider_models_when_catalog_none(self):
        provider = ClaudeProvider()
        result = list_models(provider, None)
        model_ids = [mid for mid, _ in result]
        # provider.models has fast and capable entries
        for hardcoded_id in provider.models.values():
            assert hardcoded_id in model_ids

    def test_fallback_still_ends_with_other_sentinel(self):
        provider = ClaudeProvider()
        result = list_models(provider, None)
        assert result[-1] == (OTHER_SENTINEL, "Other (type manually)")

    def test_fallback_uses_class_defaults_when_instance_models_overwritten(self):
        provider = ClaudeProvider()
        # Simulate get_provider merging a user config where capable = haiku
        provider.models = {"fast": "claude-haiku-4-5-20251001", "capable": "claude-haiku-4-5-20251001"}
        result = list_models(provider, None)
        model_ids = [mid for mid, _ in result]
        assert "claude-sonnet-4-6" in model_ids

    def test_display_name_used_when_present(self):
        provider = ClaudeProvider()
        catalog = _SAMPLE_PAYLOAD["anthropic"]["models"]
        result = list_models(provider, catalog)
        names = dict(result)
        assert names["claude-sonnet-4-6"] == "Claude Sonnet 4.6"


class TestLookupPricing:
    def test_returns_pricing_from_catalog(self):
        provider = ClaudeProvider()
        catalog = _SAMPLE_PAYLOAD["anthropic"]["models"]
        result = lookup_pricing(provider, "claude-sonnet-4-6", catalog)
        assert result == {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_write": 3.75}

    def test_returns_pricing_from_provider_dict_when_not_in_catalog(self):
        provider = ClaudeProvider()
        result = lookup_pricing(provider, "claude-sonnet-4-6", catalog=None)
        assert result == provider.pricing["claude-sonnet-4-6"]

    def test_returns_none_when_not_found_anywhere(self):
        provider = ClaudeProvider()
        result = lookup_pricing(provider, "unknown-model-xyz", catalog=None)
        assert result is None

    def test_cache_write_is_none_when_absent_from_catalog(self):
        provider = OpenCodeProvider()
        catalog = _SAMPLE_PAYLOAD["github-copilot"]["models"]
        # claude-sonnet-4.6 has no cache_write in sample payload
        result = lookup_pricing(provider, "github-copilot/claude-sonnet-4.6", catalog)
        assert result is not None
        assert result["cache_write"] is None

    def test_opencode_prefix_stripped_for_catalog_lookup(self):
        provider = OpenCodeProvider()
        catalog = _SAMPLE_PAYLOAD["github-copilot"]["models"]
        # Full model_id passed in; prefix must be stripped to find raw_id in catalog
        result = lookup_pricing(provider, "github-copilot/claude-sonnet-4.6", catalog)
        assert result is not None
        assert result["input"] == 3.0

    def test_date_suffix_stripped_for_provider_pricing_lookup(self):
        provider = ClaudeProvider()
        # claude-haiku-4-5-20251001 → strip date → claude-haiku-4-5 → found in provider.pricing
        result = lookup_pricing(provider, "claude-haiku-4-5-20251001", catalog=None)
        assert result == provider.pricing["claude-haiku-4-5"]
