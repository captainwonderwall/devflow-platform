from unittest.mock import patch

from devflow_sdk.config import DevflowConfig, GlobalConfig, ModelConfig
from devflow_sdk.config.wizard.global_steps import ProviderStep, ModelsStep


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
        with patch("devflow_sdk.config.wizard.global_steps.select", return_value="opencode"):
            result = step.run(current)
        assert result.global_config.ai_provider == "opencode"

    def test_preserves_provider_when_unchanged(self):
        step = ProviderStep()
        current = make_config(provider="opencode")
        with patch("devflow_sdk.config.wizard.global_steps.select", return_value="opencode"):
            result = step.run(current)
        assert result.global_config.ai_provider == "opencode"

    def test_other_fields_untouched(self):
        step = ProviderStep()
        current = make_config(provider="claude")
        with patch("devflow_sdk.config.wizard.global_steps.select", return_value="opencode"):
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
            patch("devflow_sdk.config.wizard.global_steps.checkbox", return_value=["fast"]),
            patch("devflow_sdk.config.wizard.global_steps.text", side_effect=["new-haiku", "0.8", "4.0", "0.08", "1.0"]),
        ):
            result = step.run(current)
        assert result.global_config.models["fast"].name == "new-haiku"

    def test_skips_unselected_tier(self):
        step = ModelsStep()
        current = make_config()
        # Only "capable" selected — "fast" should be unchanged
        with (
            patch("devflow_sdk.config.wizard.global_steps.checkbox", return_value=["capable"]),
            patch("devflow_sdk.config.wizard.global_steps.text", side_effect=["new-sonnet", "3.0", "15.0", "0.3", "3.75"]),
        ):
            result = step.run(current)
        assert result.global_config.models["fast"].name == "haiku"
        assert result.global_config.models["capable"].name == "new-sonnet"

    def test_no_tiers_selected_leaves_models_unchanged(self):
        step = ModelsStep()
        current = make_config()
        with patch("devflow_sdk.config.wizard.global_steps.checkbox", return_value=[]):
            result = step.run(current)
        assert result.global_config.models == current.global_config.models

    def test_pricing_stored_when_provided(self):
        step = ModelsStep()
        current = make_config(models={"fast": ModelConfig(name="haiku")})
        with (
            patch("devflow_sdk.config.wizard.global_steps.checkbox", return_value=["fast"]),
            patch("devflow_sdk.config.wizard.global_steps.text", side_effect=["haiku", "0.8", "4.0", "0.08", "1.0"]),
        ):
            result = step.run(current)
        pricing = result.global_config.models["fast"].pricing
        assert pricing["input"] == 0.8
        assert pricing["output"] == 4.0
        assert pricing["cache_read"] == 0.08
        assert pricing["cache_write"] == 1.0

    def test_invalid_price_reprompts_until_valid(self):
        """An invalid price string triggers a re-prompt; valid input is then accepted."""
        step = ModelsStep()
        current = make_config(models={"fast": ModelConfig(name="haiku")})
        with (
            patch("devflow_sdk.config.wizard.global_steps.checkbox", return_value=["fast"]),
            # "abc" is rejected, then "0.8" succeeds; remaining prices valid
            patch("devflow_sdk.config.wizard.global_steps.text", side_effect=["haiku", "abc", "0.8", "4.0", "0.08", "1.0"]),
            patch("builtins.print"),
        ):
            result = step.run(current)
        assert result.global_config.models["fast"].pricing["input"] == 0.8

    def test_partial_pricing_preserves_existing(self):
        """If only some price fields are filled, existing pricing is kept unchanged."""
        existing_pricing = {"input": 0.5, "output": 2.0, "cache_read": 0.05, "cache_write": 0.5}
        step = ModelsStep()
        current = make_config(models={"fast": ModelConfig(name="haiku", pricing=existing_pricing)})
        with (
            patch("devflow_sdk.config.wizard.global_steps.checkbox", return_value=["fast"]),
            # 4th price field returns "" (blank), triggering partial-fill path
            patch("devflow_sdk.config.wizard.global_steps.text", side_effect=["haiku", "0.8", "4.0", "0.08", ""]),
            patch("builtins.print"),
        ):
            result = step.run(current)
        assert result.global_config.models["fast"].pricing == existing_pricing
