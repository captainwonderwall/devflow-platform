# Model Discovery & Auto-Pricing Design

**Date:** 2026-08-26
**Status:** Approved

## Problem

`devflow-config`'s `ModelsStep` asks users to type model names and four pricing fields (input, output, cache_read, cache_write) per tier by hand. This is error-prone and requires users to look up values they shouldn't have to know.

## Goal

When a provider is selected, present a live model list sourced from the installed tool's upstream registry (`models.dev`). When the user selects a model, pre-fill pricing automatically. Free-text entry remains available for models not in the registry.

---

## Architecture

Three components change:

| Component | Change |
|---|---|
| `devflow_sdk/config/wizard/tools/model_discovery.py` | **New.** Owns all model-listing and pricing-resolution logic. No UI code. |
| `devflow_sdk/config/wizard/global_steps.py` (`ModelsStep`) | Replace free-text model entry with a `select` prompt; pre-fill pricing defaults. |
| `devflow_sdk/ai_providers/claude_provider.py`, `opencode_provider.py` | Add two class-level attributes: `models_dev_key`, `models_dev_id_prefix`. |

---

## Data Source: `models.dev/api.json`

`models.dev/api.json` is a public, structured JSON API — the same registry that OpenCode uses as its model cache. It contains pricing for all major providers. No authentication required.

Relevant provider keys:

| Provider | `models_dev_key` | Model ID format in response |
|---|---|---|
| Claude | `"anthropic"` | `"claude-sonnet-4-6"` |
| OpenCode | `"github-copilot"` | `"claude-sonnet-4.6"` (raw, without provider prefix) |

OpenCode model IDs are saved to config with a `"github-copilot/"` prefix (e.g. `"github-copilot/claude-sonnet-4.6"`), matching how `OpenCodeProvider.models` is structured today.

---

## `model_discovery.py` Interface

```python
def fetch_catalog(models_dev_key: str) -> dict[str, dict] | None:
    """Fetch models.dev/api.json and return the provider's models dict.
    Returns None on any network/parse failure (5s timeout, silent)."""

def list_models(provider: AiProvider, catalog: dict[str, dict] | None) -> list[tuple[str, str]]:
    """Return [(model_id, display_name), ..., ("__other__", "Other (type manually)")].
    model_id is fully-qualified for the config (prefix applied for OpenCode).
    Falls back to provider.models dict values if catalog is None."""

def lookup_pricing(
    provider: AiProvider,
    model_id: str,
    catalog: dict[str, dict] | None,
) -> dict | None:
    """Return {'input': float, 'output': float, 'cache_read': float, 'cache_write': float | None}
    or None if not found anywhere.
    Resolution order: catalog → provider.pricing dict → None.
    cache_write is None when absent from models.dev (some providers omit it)."""
```

`ModelsStep` calls `fetch_catalog` once per wizard run and passes the result to both `list_models` and `lookup_pricing` — no second network call.

---

## Data Flow

For each configured tier:

```
1. get_provider(current.global_config)  →  AiProvider

2. fetch_catalog(provider.models_dev_key)          [once, before tier loop]
     success → dict of model entries
     failure → None  (silent, no user-visible warning)

3. list_models(provider, catalog)
     catalog present → model list from models.dev + "Other"
     catalog None    → provider.models values + "Other"

4. select prompt  →  user picks a model
   user picks "Other"  →  text prompt for free-form model ID

5. lookup_pricing(provider, chosen_model_id, catalog)
     found in catalog      → full pricing dict
     found in provider.pricing → hardcoded dict
     not found             → None

6. _parse_price prompts for input/output/cache_read/cache_write
     pricing found → default pre-filled from dict (user can edit)
     pricing None  → empty default (existing behaviour)
```

---

## `ModelsStep` Changes (pseudocode)

```python
def run(self, current: DevflowConfig) -> DevflowConfig:
    provider = get_provider(current.global_config)
    catalog = fetch_catalog(provider.models_dev_key)        # one network call

    # tier selection — unchanged
    selected_tiers = checkbox("Select model tiers to configure:", ...)

    updated_models = dict(existing)
    for tier in selected_tiers:
        model_choices = list_models(provider, catalog)

        chosen = select(f"{tier.capitalize()} model:", choices=model_choices)
        if chosen is None:
            continue
        if chosen == "__other__":
            chosen = text(f"{tier.capitalize()} model name:", default=current_name)
            if chosen is None:
                continue

        pricing = lookup_pricing(provider, chosen, catalog)

        input_price  = _parse_price("Input price ($/M tokens):",
                           default=str(pricing["input"]) if pricing else "")
        output_price = _parse_price("Output price ($/M tokens):",
                           default=str(pricing["output"]) if pricing else "")
        cache_read   = _parse_price("Cache read price ($/M tokens):",
                           default=str(pricing["cache_read"]) if pricing else "")
        cache_write  = _parse_price("Cache write price ($/M tokens):",
                           default=str(pricing["cache_write"]) if pricing and pricing["cache_write"] is not None else "")
        ...
```

`_parse_price` and partial-fill handling are unchanged.

---

## Provider Class Changes

Two new class-level attributes on `AiProvider` (base class gets empty-string defaults):

```python
class AiProvider(ABC):
    models_dev_key: str = ""
    models_dev_id_prefix: str = ""
    ...

class ClaudeProvider(AiProvider):
    models_dev_key = "anthropic"
    models_dev_id_prefix = ""           # IDs saved as-is: "claude-sonnet-4-6"

class OpenCodeProvider(AiProvider):
    models_dev_key = "github-copilot"
    models_dev_id_prefix = "github-copilot/"   # IDs saved as: "github-copilot/claude-sonnet-4.6"
```

No method changes on either class.

---

## Error Handling

`fetch_catalog` catches all exceptions — `requests.RequestException`, `json.JSONDecodeError`, `KeyError`, `TimeoutError` — and returns `None`. No exception propagates to the wizard. The 5-second timeout is the worst-case user-visible delay, after which the wizard continues with the hardcoded fallback list silently.

---

## Testing

`fetch_catalog` is the single I/O boundary. Tests mock it; no live network calls.

| Test | What it covers |
|---|---|
| `list_models` with valid catalog | Correct `(id, display_name)` list, prefix applied for OpenCode |
| `list_models` with `catalog=None` | Falls back to `provider.models` values + "Other" |
| `lookup_pricing` — model in catalog | Full dict returned |
| `lookup_pricing` — model in `provider.pricing` only | Hardcoded dict returned |
| `lookup_pricing` — model in neither | `None` returned |
| `lookup_pricing` — `cache_write` absent from catalog | Dict with `cache_write=None` |
| `ModelsStep` integration | Mock `fetch_catalog`; assert pricing defaults pre-filled in `_parse_price` calls |

Existing `ModelsStep` tests need updating: drive the `select` prompt for model name instead of the `text` prompt. That is the only breaking change to the test surface.

---

## Files Affected

| File | Change |
|---|---|
| `devflow_sdk/config/wizard/tools/model_discovery.py` | **New file** |
| `devflow_sdk/config/wizard/global_steps.py` | Replace free-text model entry with `select`; pre-fill pricing |
| `devflow_sdk/ai_providers/base.py` | Add `models_dev_key`, `models_dev_id_prefix` attributes |
| `devflow_sdk/ai_providers/claude_provider.py` | Set `models_dev_key = "anthropic"`, `models_dev_id_prefix = ""` |
| `devflow_sdk/ai_providers/opencode_provider.py` | Set `models_dev_key = "github-copilot"`, `models_dev_id_prefix = "github-copilot/"` |
| `devflow_sdk/tests/test_wizard_global_steps.py` | Update model-name prompt assertions to use `select` |
| `devflow_sdk/tests/test_model_discovery.py` | **New file** — unit tests for `model_discovery` |
