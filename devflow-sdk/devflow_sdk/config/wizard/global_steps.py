from __future__ import annotations

import dataclasses

from devflow_sdk.config.schema import DevflowConfig, ModelConfig
from devflow_sdk.config.wizard import WizardStep
from devflow_sdk.prompts import Choice, checkbox, select, text

_PROVIDER_CHOICES = ["claude", "opencode"]


def _parse_price(label: str, default: str) -> float | None:
    """Prompt for a price value, re-prompting on non-numeric input.
    Returns the parsed float, or None if the user cancelled or left it blank."""
    while True:
        raw = text(label, default=default)
        if raw is None or raw == "":
            return None
        try:
            return float(raw)
        except ValueError:
            print(f"  '{raw}' is not a valid number.")


class ProviderStep(WizardStep):
    section = "AI Provider"

    def run(self, current: DevflowConfig) -> DevflowConfig:
        current_provider = current.global_config.ai_provider
        choices = [
            Choice(p, checked=(p == current_provider))
            for p in _PROVIDER_CHOICES
        ]
        provider = select("Which AI provider should devflow use?", choices=choices)
        if provider is None:
            return current
        return dataclasses.replace(
            current,
            global_config=dataclasses.replace(current.global_config, ai_provider=provider),
        )


class ModelsStep(WizardStep):
    section = "Model Configuration"

    def run(self, current: DevflowConfig) -> DevflowConfig:
        existing = current.global_config.models
        tier_choices = [
            Choice(
                f"{tier.capitalize()}  (current: {existing[tier].name if tier in existing else 'not set'})",
                value=tier,
                checked=True,
            )
            for tier in ("fast", "capable")
        ]
        selected_tiers = checkbox("Select model tiers to configure:", choices=tier_choices, allow_empty=True)
        if not selected_tiers:
            return current

        updated_models = dict(existing)
        for tier in selected_tiers:
            current_name = existing[tier].name if tier in existing else ""
            current_pricing = existing[tier].pricing if tier in existing else None

            name = text(f"{tier.capitalize()} model name:", default=current_name)
            if name is None:
                continue

            input_price = _parse_price(
                f"{tier.capitalize()} input price ($/M tokens):",
                default=str(current_pricing["input"]) if current_pricing else "",
            )
            output_price = _parse_price(
                f"{tier.capitalize()} output price ($/M tokens):",
                default=str(current_pricing["output"]) if current_pricing else "",
            )
            cache_read_price = _parse_price(
                f"{tier.capitalize()} cache read price ($/M tokens):",
                default=str(current_pricing["cache_read"]) if current_pricing else "",
            )
            cache_write_price = _parse_price(
                f"{tier.capitalize()} cache write price ($/M tokens):",
                default=str(current_pricing["cache_write"]) if current_pricing else "",
            )

            all_prices = [input_price, output_price, cache_read_price, cache_write_price]
            if all(p is not None for p in all_prices):
                pricing: dict | None = {
                    "input": input_price,
                    "output": output_price,
                    "cache_read": cache_read_price,
                    "cache_write": cache_write_price,
                }
            elif all(p is None for p in all_prices):
                # All fields blank — preserve whatever was already there
                pricing = current_pricing
            else:
                # Partial fill — warn and preserve existing pricing
                print(f"  Partial pricing input — preserving existing pricing for {tier}.")
                pricing = current_pricing

            updated_models[tier] = ModelConfig(name=name, pricing=pricing)

        return dataclasses.replace(
            current,
            global_config=dataclasses.replace(current.global_config, models=updated_models),
        )
