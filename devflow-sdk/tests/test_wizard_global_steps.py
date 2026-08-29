from unittest.mock import patch

from devflow_sdk.core.config import DevflowConfig, GlobalConfig, ModelConfig
from devflow_sdk.core.config.wizard.global_steps import ProviderStep, ModelsStep
from devflow_sdk.core.config.wizard.tools.model_discovery import OTHER_SENTINEL


def make_config(provider="claude", models=None):
    return DevflowConfig(
        global_config=GlobalConfig(
            ai_provider=provider,
            models=models or {
                "fast": ModelConfig(name="haiku"),
                "capable": ModelConfig(name="sonnet"),
            },
        )
    )


class TestProviderStep:
    def test_section_label(self):
        assert ProviderStep().section == "AI Provider"

    def test_switches_provider_to_opencode(self):
        step = ProviderStep()
        current = make_config(provider="claude")
        # select() returns "opencode" — simulate user choosing opencode
        with patch("devflow_sdk.core.config.wizard.global_steps.select", return_value="opencode"):
            result = step.run(current)
        assert result.global_config.ai_provider == "opencode"

    def test_preserves_provider_when_unchanged(self):
        step = ProviderStep()
        current = make_config(provider="opencode")
        with patch("devflow_sdk.core.config.wizard.global_steps.select", return_value="opencode"):
            result = step.run(current)
        assert result.global_config.ai_provider == "opencode"

    def test_other_fields_untouched(self):
        step = ProviderStep()
        current = make_config(provider="claude")
        with patch("devflow_sdk.core.config.wizard.global_steps.select", return_value="opencode"):
            result = step.run(current)
        assert result.global_config.models == current.global_config.models
        assert result.tools == current.tools


class TestModelsStep:
    def test_section_label(self):
        assert ModelsStep().section == "Model Configuration"

    def test_updates_fast_model_name(self):
        step = ModelsStep()
        current = make_config()
        with (
            patch("devflow_sdk.core.config.wizard.global_steps.checkbox", return_value=["fast"]),
            patch("devflow_sdk.core.config.wizard.global_steps.fetch_catalog", return_value=None),
            patch("devflow_sdk.core.config.wizard.global_steps.select", return_value="new-haiku"),
            patch("devflow_sdk.core.config.wizard.global_steps.text", side_effect=["0.8", "4.0", "0.08", "1.0"]),
        ):
            result = step.run(current)
        assert result.global_config.models["fast"].name == "new-haiku"

    def test_skips_unselected_tier(self):
        step = ModelsStep()
        current = make_config()
        with (
            patch("devflow_sdk.core.config.wizard.global_steps.checkbox", return_value=["capable"]),
            patch("devflow_sdk.core.config.wizard.global_steps.fetch_catalog", return_value=None),
            patch("devflow_sdk.core.config.wizard.global_steps.select", return_value="new-sonnet"),
            patch("devflow_sdk.core.config.wizard.global_steps.text", side_effect=["3.0", "15.0", "0.3", "3.75"]),
        ):
            result = step.run(current)
        assert result.global_config.models["fast"].name == "haiku"
        assert result.global_config.models["capable"].name == "new-sonnet"

    def test_no_tiers_selected_leaves_models_unchanged(self):
        step = ModelsStep()
        current = make_config()
        with patch("devflow_sdk.core.config.wizard.global_steps.checkbox", return_value=[]):
            result = step.run(current)
        assert result.global_config.models == current.global_config.models

    def test_pricing_stored_when_provided(self):
        step = ModelsStep()
        current = make_config(models={"fast": ModelConfig(name="haiku")})
        with (
            patch("devflow_sdk.core.config.wizard.global_steps.checkbox", return_value=["fast"]),
            patch("devflow_sdk.core.config.wizard.global_steps.fetch_catalog", return_value=None),
            patch("devflow_sdk.core.config.wizard.global_steps.select", return_value="haiku"),
            patch("devflow_sdk.core.config.wizard.global_steps.text", side_effect=["0.8", "4.0", "0.08", "1.0"]),
        ):
            result = step.run(current)
        pricing = result.global_config.models["fast"].pricing
        assert pricing["input"] == 0.8
        assert pricing["output"] == 4.0
        assert pricing["cache_read"] == 0.08
        assert pricing["cache_write"] == 1.0

    def test_other_option_falls_back_to_text_prompt(self):
        """When user selects 'Other', a text prompt collects the model name."""
        step = ModelsStep()
        current = make_config(models={"fast": ModelConfig(name="haiku")})
        with (
            patch("devflow_sdk.core.config.wizard.global_steps.checkbox", return_value=["fast"]),
            patch("devflow_sdk.core.config.wizard.global_steps.fetch_catalog", return_value=None),
            patch("devflow_sdk.core.config.wizard.global_steps.select", return_value=OTHER_SENTINEL),
            patch("devflow_sdk.core.config.wizard.global_steps.text", side_effect=["custom-model", "1.0", "5.0", "0.1", "1.25"]),
        ):
            result = step.run(current)
        assert result.global_config.models["fast"].name == "custom-model"

    def test_pricing_prefilled_from_catalog(self):
        """When catalog has pricing for selected model, defaults are pre-filled."""
        step = ModelsStep()
        current = make_config(models={"fast": ModelConfig(name="claude-haiku-4-5")})
        catalog = {
            "claude-haiku-4-5": {
                "name": "Claude Haiku 4.5",
                "cost": {"input": 1.0, "output": 5.0, "cache_read": 0.1, "cache_write": 1.25},
            }
        }
        with (
            patch("devflow_sdk.core.config.wizard.global_steps.checkbox", return_value=["fast"]),
            patch("devflow_sdk.core.config.wizard.global_steps.fetch_catalog", return_value=catalog),
            patch("devflow_sdk.core.config.wizard.global_steps.select", return_value="claude-haiku-4-5"),
            # User confirms pre-filled defaults by entering the same values
            patch("devflow_sdk.core.config.wizard.global_steps.text", side_effect=["1.0", "5.0", "0.1", "1.25"]),
        ):
            result = step.run(current)
        pricing = result.global_config.models["fast"].pricing
        assert pricing["input"] == 1.0
        assert pricing["output"] == 5.0
        assert pricing["cache_read"] == 0.1
        assert pricing["cache_write"] == 1.25

    def test_invalid_price_reprompts_until_valid(self):
        step = ModelsStep()
        current = make_config(models={"fast": ModelConfig(name="haiku")})
        with (
            patch("devflow_sdk.core.config.wizard.global_steps.checkbox", return_value=["fast"]),
            patch("devflow_sdk.core.config.wizard.global_steps.fetch_catalog", return_value=None),
            patch("devflow_sdk.core.config.wizard.global_steps.select", return_value="haiku"),
            patch("devflow_sdk.core.config.wizard.global_steps.text", side_effect=["abc", "0.8", "4.0", "0.08", "1.0"]),
            patch("builtins.print"),
        ):
            result = step.run(current)
        assert result.global_config.models["fast"].pricing["input"] == 0.8

    def test_partial_pricing_preserves_existing(self):
        existing_pricing = {"input": 0.5, "output": 2.0, "cache_read": 0.05, "cache_write": 0.5}
        step = ModelsStep()
        current = make_config(models={"fast": ModelConfig(name="haiku", pricing=existing_pricing)})
        with (
            patch("devflow_sdk.core.config.wizard.global_steps.checkbox", return_value=["fast"]),
            patch("devflow_sdk.core.config.wizard.global_steps.fetch_catalog", return_value=None),
            patch("devflow_sdk.core.config.wizard.global_steps.select", return_value="haiku"),
            patch("devflow_sdk.core.config.wizard.global_steps.text", side_effect=["0.8", "4.0", "0.08", ""]),
            patch("builtins.print"),
        ):
            result = step.run(current)
        assert result.global_config.models["fast"].pricing == existing_pricing
