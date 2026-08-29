import json
import re
from pathlib import Path
from devflow_sdk.core.ai.providers.base import AiProvider

OTHER_SENTINEL = "__other__"
_DATE_SUFFIX_RE = re.compile(r'-\d{8}$')
_CATALOG_PATH = Path(__file__).parent / "models_catalog.json"


def fetch_catalog(models_dev_key: str) -> dict[str, dict] | None:
    try:
        with open(_CATALOG_PATH) as f:
            data = json.load(f)
        return data[models_dev_key].get("models", {})
    except Exception:
        return None


def list_models(provider: AiProvider, catalog: dict[str, dict] | None) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    if catalog:
        for raw_id, model_data in catalog.items():
            full_id = provider.models_dev_id_prefix + raw_id
            display = model_data.get("name") or raw_id
            entries.append((full_id, display))
    else:
        for model_id in type(provider).models.values():
            entries.append((model_id, model_id))
    entries.append((OTHER_SENTINEL, "Other (type manually)"))
    return entries


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
