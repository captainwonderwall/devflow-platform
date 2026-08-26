# Model Discovery & Auto-Pricing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace free-text model entry in `devflow-config`'s wizard with a live model select backed by `models.dev`, with pricing auto-filled from the same source.

**Architecture:** A new `model_discovery.py` module in the wizard tools layer fetches `models.dev/api.json` and owns the full resolution chain (catalog → hardcoded fallback → None). `ModelsStep` calls this module and switches from a `text` prompt to a `select` prompt for model names. Provider classes gain two class-level attributes (`models_dev_key`, `models_dev_id_prefix`) so `model_discovery` can stay provider-agnostic.

**Tech Stack:** Python 3.11+, `urllib.request` (stdlib — no new deps), `questionary` (already a dep), `pytest`.

**Spec:** `docs/superpowers/specs/2026-08-26-model-discovery-design.md`

## Global Constraints

- No new runtime dependencies — use `urllib.request` (stdlib) for HTTP.
- Python 3.11+ (`dict | None` union syntax is fine).
- All tests live in `devflow-sdk/tests/` (flat, no subdirectories).
- Do not commit any changes unless explicitly asked.

---

## File Map

| File | Status | Responsibility |
|---|---|---|
| `devflow_sdk/ai_providers/base.py` | Modify | Add `models_dev_key` and `models_dev_id_prefix` class attrs |
| `devflow_sdk/ai_providers/claude_provider.py` | Modify | Set `models_dev_key = "anthropic"`, `models_dev_id_prefix = ""` |
| `devflow_sdk/ai_providers/opencode_provider.py` | Modify | Set `models_dev_key = "github-copilot"`, `models_dev_id_prefix = "github-copilot/"` |
| `devflow_sdk/config/wizard/tools/model_discovery.py` | **Create** | `fetch_catalog`, `list_models`, `lookup_pricing`, `OTHER_SENTINEL` |
| `devflow_sdk/config/wizard/global_steps.py` | Modify | Switch model entry to `select`; pre-fill pricing defaults |
| `tests/test_model_discovery.py` | **Create** | Unit tests for all three `model_discovery` functions |
| `tests/test_wizard_global_steps.py` | Modify | Update `ModelsStep` tests to drive `select` instead of `text` for model name |

All paths are relative to `devflow-sdk/`.

---

### Task 1: Provider class attributes

Add `models_dev_key` and `models_dev_id_prefix` to the provider hierarchy.

**Files:**
- Modify: `devflow_sdk/ai_providers/base.py`
- Modify: `devflow_sdk/ai_providers/claude_provider.py`
- Modify: `devflow_sdk/ai_providers/opencode_provider.py`
- Test: `tests/test_ai_providers.py`

**Interfaces:**
- Produces: `AiProvider.models_dev_key: str`, `AiProvider.models_dev_id_prefix: str` — used by Task 2 (`model_discovery`) and Task 4 (`ModelsStep`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_ai_providers.py`:

```python
from devflow_sdk.ai_providers.claude_provider import ClaudeProvider
from devflow_sdk.ai_providers.opencode_provider import OpenCodeProvider

class TestProviderAttributes:
    def test_claude_models_dev_key(self):
        assert ClaudeProvider().models_dev_key == "anthropic"

    def test_claude_models_dev_id_prefix(self):
        assert ClaudeProvider().models_dev_id_prefix == ""

    def test_opencode_models_dev_key(self):
        assert OpenCodeProvider().models_dev_key == "github-copilot"

    def test_opencode_models_dev_id_prefix(self):
        assert OpenCodeProvider().models_dev_id_prefix == "github-copilot/"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd devflow-sdk && python -m pytest tests/test_ai_providers.py::TestProviderAttributes -v
```

Expected: `AttributeError: 'ClaudeProvider' object has no attribute 'models_dev_key'`

- [ ] **Step 3: Add attributes to `base.py`**

In `devflow_sdk/ai_providers/base.py`, add two class-level attributes after `redact_after_flags`:

```python
class AiProvider(ABC):
    name: str
    binary: str
    models: dict[str, str]
    pricing: dict[str, dict]
    install_hint: str = ""
    display_name: str = ""
    redact_after_flags: tuple = ("-p",)
    models_dev_key: str = ""
    models_dev_id_prefix: str = ""
```

- [ ] **Step 4: Set attributes on `ClaudeProvider`**

In `devflow_sdk/ai_providers/claude_provider.py`, add after `install_hint`:

```python
class ClaudeProvider(AiProvider):
    name = "claude"
    binary = "claude"
    display_name = "Claude"
    install_hint = "https://claude.ai/code"
    models_dev_key = "anthropic"
    models_dev_id_prefix = ""
    models = { ... }   # unchanged
```

- [ ] **Step 5: Set attributes on `OpenCodeProvider`**

In `devflow_sdk/ai_providers/opencode_provider.py`, add after `install_hint`:

```python
class OpenCodeProvider(AiProvider):
    name = "opencode"
    binary = "opencode"
    display_name = "OpenCode"
    install_hint = "https://opencode.ai"
    models_dev_key = "github-copilot"
    models_dev_id_prefix = "github-copilot/"
    models = { ... }   # unchanged
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd devflow-sdk && python -m pytest tests/test_ai_providers.py::TestProviderAttributes -v
```

Expected: 4 PASS

---

### Task 2: `fetch_catalog`

Create `model_discovery.py` with the single HTTP I/O boundary.

**Files:**
- Create: `devflow_sdk/config/wizard/tools/model_discovery.py`
- Test: `tests/test_model_discovery.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks (standalone).
- Produces: `fetch_catalog(models_dev_key: str) -> dict[str, dict] | None` — used by Tasks 3, 4, and 5.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_model_discovery.py`:

```python
import json
from unittest.mock import MagicMock, patch

from devflow_sdk.config.wizard.tools.model_discovery import fetch_catalog


def _make_urlopen_mock(payload: dict) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(payload).encode()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    return MagicMock(return_value=mock_resp)


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
    def test_returns_models_dict_for_known_key(self):
        with patch(
            "devflow_sdk.config.wizard.tools.model_discovery.urllib.request.urlopen",
            _make_urlopen_mock(_SAMPLE_PAYLOAD),
        ):
            result = fetch_catalog("anthropic")
        assert "claude-sonnet-4-6" in result
        assert result["claude-sonnet-4-6"]["name"] == "Claude Sonnet 4.6"

    def test_returns_none_on_network_error(self):
        with patch(
            "devflow_sdk.config.wizard.tools.model_discovery.urllib.request.urlopen",
            side_effect=OSError("network down"),
        ):
            result = fetch_catalog("anthropic")
        assert result is None

    def test_returns_none_on_bad_json(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not json {"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch(
            "devflow_sdk.config.wizard.tools.model_discovery.urllib.request.urlopen",
            MagicMock(return_value=mock_resp),
        ):
            result = fetch_catalog("anthropic")
        assert result is None

    def test_returns_none_for_missing_provider_key(self):
        with patch(
            "devflow_sdk.config.wizard.tools.model_discovery.urllib.request.urlopen",
            _make_urlopen_mock({"other": {}}),
        ):
            result = fetch_catalog("anthropic")
        assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd devflow-sdk && python -m pytest tests/test_model_discovery.py::TestFetchCatalog -v
```

Expected: `ModuleNotFoundError: No module named 'devflow_sdk.config.wizard.tools.model_discovery'`

- [ ] **Step 3: Implement `fetch_catalog`**

Create `devflow_sdk/config/wizard/tools/model_discovery.py`:

```python
import json
import urllib.request
from devflow_sdk.ai_providers.base import AiProvider

MODELS_DEV_URL = "https://models.dev/api.json"
_TIMEOUT = 5
OTHER_SENTINEL = "__other__"


def fetch_catalog(models_dev_key: str) -> dict[str, dict] | None:
    try:
        with urllib.request.urlopen(MODELS_DEV_URL, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read())
        return data[models_dev_key].get("models", {})
    except Exception:
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd devflow-sdk && python -m pytest tests/test_model_discovery.py::TestFetchCatalog -v
```

Expected: 4 PASS

---

### Task 3: `list_models`

Add model listing to `model_discovery.py`.

**Files:**
- Modify: `devflow_sdk/config/wizard/tools/model_discovery.py`
- Test: `tests/test_model_discovery.py`

**Interfaces:**
- Consumes: `fetch_catalog` (Task 2), `AiProvider.models_dev_id_prefix` and `AiProvider.models` (Task 1), `OTHER_SENTINEL` (Task 2).
- Produces: `list_models(provider: AiProvider, catalog: dict[str, dict] | None) -> list[tuple[str, str]]` — used by Task 5.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_model_discovery.py`:

```python
from devflow_sdk.config.wizard.tools.model_discovery import list_models, OTHER_SENTINEL
from devflow_sdk.ai_providers.claude_provider import ClaudeProvider
from devflow_sdk.ai_providers.opencode_provider import OpenCodeProvider


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

    def test_display_name_used_when_present(self):
        provider = ClaudeProvider()
        catalog = _SAMPLE_PAYLOAD["anthropic"]["models"]
        result = list_models(provider, catalog)
        names = dict(result)
        assert names["claude-sonnet-4-6"] == "Claude Sonnet 4.6"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd devflow-sdk && python -m pytest tests/test_model_discovery.py::TestListModels -v
```

Expected: `ImportError: cannot import name 'list_models'`

- [ ] **Step 3: Implement `list_models`**

Add to `devflow_sdk/config/wizard/tools/model_discovery.py`:

```python
def list_models(provider: AiProvider, catalog: dict[str, dict] | None) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    if catalog:
        for raw_id, model_data in catalog.items():
            full_id = provider.models_dev_id_prefix + raw_id
            display = model_data.get("name") or raw_id
            entries.append((full_id, display))
    else:
        for model_id in provider.models.values():
            entries.append((model_id, model_id))
    entries.append((OTHER_SENTINEL, "Other (type manually)"))
    return entries
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd devflow-sdk && python -m pytest tests/test_model_discovery.py::TestListModels -v
```

Expected: 6 PASS

---

### Task 4: `lookup_pricing`

Add pricing resolution to `model_discovery.py`.

**Files:**
- Modify: `devflow_sdk/config/wizard/tools/model_discovery.py`
- Test: `tests/test_model_discovery.py`

**Interfaces:**
- Consumes: `AiProvider.models_dev_id_prefix`, `AiProvider.pricing` (Task 1), catalog from `fetch_catalog` (Task 2).
- Produces: `lookup_pricing(provider: AiProvider, model_id: str, catalog: dict[str, dict] | None) -> dict | None` — used by Task 5.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_model_discovery.py`:

```python
from devflow_sdk.config.wizard.tools.model_discovery import lookup_pricing


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd devflow-sdk && python -m pytest tests/test_model_discovery.py::TestLookupPricing -v
```

Expected: `ImportError: cannot import name 'lookup_pricing'`

- [ ] **Step 3: Implement `lookup_pricing`**

Add to `devflow_sdk/config/wizard/tools/model_discovery.py`:

```python
import re

_DATE_SUFFIX_RE = re.compile(r'-\d{8}$')


def lookup_pricing(
    provider: AiProvider,
    model_id: str,
    catalog: dict[str, dict] | None,
) -> dict | None:
    # Strip provider prefix to get the raw catalog key
    raw_id = model_id
    if provider.models_dev_id_prefix and model_id.startswith(provider.models_dev_id_prefix):
        raw_id = model_id[len(provider.models_dev_id_prefix):]

    # 1. Check catalog
    if catalog and raw_id in catalog:
        cost = catalog[raw_id].get("cost", {})
        if cost:
            return {
                "input": cost.get("input"),
                "output": cost.get("output"),
                "cache_read": cost.get("cache_read"),
                "cache_write": cost.get("cache_write"),  # None when absent
            }

    # 2. Check provider.pricing — try full id, then date-stripped version
    normalized = _DATE_SUFFIX_RE.sub('', raw_id)
    for key in (raw_id, normalized, model_id):
        if key in provider.pricing:
            return provider.pricing[key]

    return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd devflow-sdk && python -m pytest tests/test_model_discovery.py::TestLookupPricing -v
```

Expected: 6 PASS

- [ ] **Step 5: Run all model_discovery tests**

```bash
cd devflow-sdk && python -m pytest tests/test_model_discovery.py -v
```

Expected: all 16 PASS

---

### Task 5: Update `ModelsStep`

Replace free-text model entry with `select`; pre-fill pricing defaults.

**Files:**
- Modify: `devflow_sdk/config/wizard/global_steps.py`
- Test: `tests/test_wizard_global_steps.py`

**Interfaces:**
- Consumes: `fetch_catalog`, `list_models`, `lookup_pricing`, `OTHER_SENTINEL` from Task 2–4; `get_provider` from `devflow_sdk.ai_providers`.

- [ ] **Step 1: Update the existing `ModelsStep` tests**

Replace the entire `TestModelsStep` class in `tests/test_wizard_global_steps.py`. All tests now patch `fetch_catalog` (to avoid live network calls) and drive model selection via `select` instead of the first `text` call:

```python
from devflow_sdk.config.wizard.tools.model_discovery import OTHER_SENTINEL


class TestModelsStep:
    def test_section_label(self):
        assert ModelsStep().section == "Model Configuration"

    def test_updates_fast_model_name(self):
        step = ModelsStep()
        current = make_config()
        with (
            patch("devflow_sdk.config.wizard.global_steps.checkbox", return_value=["fast"]),
            patch("devflow_sdk.config.wizard.global_steps.fetch_catalog", return_value=None),
            patch("devflow_sdk.config.wizard.global_steps.select", return_value="new-haiku"),
            patch("devflow_sdk.config.wizard.global_steps.text", side_effect=["0.8", "4.0", "0.08", "1.0"]),
        ):
            result = step.run(current)
        assert result.global_config.models["fast"].name == "new-haiku"

    def test_skips_unselected_tier(self):
        step = ModelsStep()
        current = make_config()
        with (
            patch("devflow_sdk.config.wizard.global_steps.checkbox", return_value=["capable"]),
            patch("devflow_sdk.config.wizard.global_steps.fetch_catalog", return_value=None),
            patch("devflow_sdk.config.wizard.global_steps.select", return_value="new-sonnet"),
            patch("devflow_sdk.config.wizard.global_steps.text", side_effect=["3.0", "15.0", "0.3", "3.75"]),
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
            patch("devflow_sdk.config.wizard.global_steps.fetch_catalog", return_value=None),
            patch("devflow_sdk.config.wizard.global_steps.select", return_value="haiku"),
            patch("devflow_sdk.config.wizard.global_steps.text", side_effect=["0.8", "4.0", "0.08", "1.0"]),
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
            patch("devflow_sdk.config.wizard.global_steps.checkbox", return_value=["fast"]),
            patch("devflow_sdk.config.wizard.global_steps.fetch_catalog", return_value=None),
            patch("devflow_sdk.config.wizard.global_steps.select", return_value=OTHER_SENTINEL),
            patch("devflow_sdk.config.wizard.global_steps.text", side_effect=["custom-model", "1.0", "5.0", "0.1", "1.25"]),
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
            patch("devflow_sdk.config.wizard.global_steps.checkbox", return_value=["fast"]),
            patch("devflow_sdk.config.wizard.global_steps.fetch_catalog", return_value=catalog),
            patch("devflow_sdk.config.wizard.global_steps.select", return_value="claude-haiku-4-5"),
            # User confirms pre-filled defaults by entering the same values
            patch("devflow_sdk.config.wizard.global_steps.text", side_effect=["1.0", "5.0", "0.1", "1.25"]),
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
            patch("devflow_sdk.config.wizard.global_steps.checkbox", return_value=["fast"]),
            patch("devflow_sdk.config.wizard.global_steps.fetch_catalog", return_value=None),
            patch("devflow_sdk.config.wizard.global_steps.select", return_value="haiku"),
            patch("devflow_sdk.config.wizard.global_steps.text", side_effect=["abc", "0.8", "4.0", "0.08", "1.0"]),
            patch("builtins.print"),
        ):
            result = step.run(current)
        assert result.global_config.models["fast"].pricing["input"] == 0.8

    def test_partial_pricing_preserves_existing(self):
        existing_pricing = {"input": 0.5, "output": 2.0, "cache_read": 0.05, "cache_write": 0.5}
        step = ModelsStep()
        current = make_config(models={"fast": ModelConfig(name="haiku", pricing=existing_pricing)})
        with (
            patch("devflow_sdk.config.wizard.global_steps.checkbox", return_value=["fast"]),
            patch("devflow_sdk.config.wizard.global_steps.fetch_catalog", return_value=None),
            patch("devflow_sdk.config.wizard.global_steps.select", return_value="haiku"),
            patch("devflow_sdk.config.wizard.global_steps.text", side_effect=["0.8", "4.0", "0.08", ""]),
            patch("builtins.print"),
        ):
            result = step.run(current)
        assert result.global_config.models["fast"].pricing == existing_pricing
```

- [ ] **Step 2: Run updated tests to confirm they fail (expected — `ModelsStep` not yet updated)**

```bash
cd devflow-sdk && python -m pytest tests/test_wizard_global_steps.py::TestModelsStep -v
```

Expected: failures because `ModelsStep` still uses `text` for model name and doesn't call `fetch_catalog`.

- [ ] **Step 3: Implement the updated `ModelsStep`**

Replace the contents of `devflow_sdk/config/wizard/global_steps.py` with:

```python
from __future__ import annotations

import dataclasses

from devflow_sdk.ai_providers import get_provider
from devflow_sdk.config.schema import DevflowConfig, ModelConfig
from devflow_sdk.config.wizard import WizardStep
from devflow_sdk.config.wizard.tools.model_discovery import (
    OTHER_SENTINEL,
    fetch_catalog,
    list_models,
    lookup_pricing,
)
from devflow_sdk.prompts import Choice, checkbox, select, text

_PROVIDER_CHOICES = ["claude", "opencode"]


def _parse_price(label: str, default: str) -> float | None:
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

        provider = get_provider(current.global_config)
        catalog = fetch_catalog(provider.models_dev_key)

        updated_models = dict(existing)
        for tier in selected_tiers:
            current_name = existing[tier].name if tier in existing else ""
            current_pricing = existing[tier].pricing if tier in existing else None

            model_entries = list_models(provider, catalog)
            model_ids = [mid for mid, _ in model_entries]
            pre_selected = current_name if current_name in model_ids else OTHER_SENTINEL
            model_choices = [
                Choice(title=display, value=mid, checked=(mid == pre_selected))
                for mid, display in model_entries
            ]

            chosen = select(f"{tier.capitalize()} model:", choices=model_choices)
            if chosen is None:
                continue
            if chosen == OTHER_SENTINEL:
                chosen = text(f"{tier.capitalize()} model name:", default=current_name)
                if chosen is None:
                    continue

            pricing = lookup_pricing(provider, chosen, catalog)

            def _price_default(key: str, p: dict | None = pricing, cp: dict | None = current_pricing) -> str:
                if p and p.get(key) is not None:
                    return str(p[key])
                if cp and cp.get(key) is not None:
                    return str(cp[key])
                return ""

            input_price = _parse_price(f"{tier.capitalize()} input price ($/M tokens):", default=_price_default("input"))
            output_price = _parse_price(f"{tier.capitalize()} output price ($/M tokens):", default=_price_default("output"))
            cache_read_price = _parse_price(f"{tier.capitalize()} cache read price ($/M tokens):", default=_price_default("cache_read"))
            cache_write_price = _parse_price(f"{tier.capitalize()} cache write price ($/M tokens):", default=_price_default("cache_write"))

            all_prices = [input_price, output_price, cache_read_price, cache_write_price]
            if all(p is not None for p in all_prices):
                new_pricing: dict | None = {
                    "input": input_price,
                    "output": output_price,
                    "cache_read": cache_read_price,
                    "cache_write": cache_write_price,
                }
            elif all(p is None for p in all_prices):
                new_pricing = current_pricing
            else:
                print(f"  Partial pricing input — preserving existing pricing for {tier}.")
                new_pricing = current_pricing

            updated_models[tier] = ModelConfig(name=chosen, pricing=new_pricing)

        return dataclasses.replace(
            current,
            global_config=dataclasses.replace(current.global_config, models=updated_models),
        )
```

- [ ] **Step 4: Run all `global_steps` tests**

```bash
cd devflow-sdk && python -m pytest tests/test_wizard_global_steps.py -v
```

Expected: all PASS (both `TestProviderStep` and `TestModelsStep`)

- [ ] **Step 5: Run the full test suite**

```bash
cd devflow-sdk && python -m pytest -v
```

Expected: all PASS. If any pre-existing tests fail, investigate before proceeding.
