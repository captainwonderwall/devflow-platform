#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT="$REPO_ROOT/devflow-sdk/devflow_sdk/core/config/wizard/tools/models_catalog.json"
MODELS_DEV_REPO="${MODELS_DEV_REPO:-sst/models.dev}"

echo "==> Fetching models catalog from models.dev GitHub repo ($MODELS_DEV_REPO)..."

python3 - "$OUTPUT" "$MODELS_DEV_REPO" <<'PYEOF'
import json
import os
import re
import subprocess
import sys

output_path, repo = sys.argv[1], sys.argv[2]
DATE_SUFFIX_RE = re.compile(r'-\d{8}$')

def curl_fetch(url):
    headers = ["-H", "User-Agent: devflow-sdk"]
    if token := os.environ.get("GITHUB_TOKEN"):
        headers += ["-H", f"Authorization: Bearer {token}"]
    result = subprocess.run(
        ["curl", "-fsSL", "--max-time", "30"] + headers + [url],
        capture_output=True, check=True,
    )
    return result.stdout.decode()

def github_list(path):
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    return json.loads(curl_fetch(url))

def parse_toml_cost(text):
    """Extract [cost] section fields (simple line-by-line; skips tiers)."""
    cost = {}
    in_cost = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "[cost]":
            in_cost = True
            continue
        if in_cost and stripped.startswith("["):
            break  # next section or [[cost.tiers]]
        if in_cost and "=" in stripped and not stripped.startswith("#"):
            key, _, val = stripped.partition("=")
            key = key.strip()
            val = val.strip()
            if key in ("input", "output", "cache_read", "cache_write"):
                try:
                    cost[key] = float(val)
                except ValueError:
                    pass
    return cost

def parse_toml_field(text, field):
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{field} ="):
            _, _, val = stripped.partition("=")
            return val.strip().strip('"')
    return None

def model_name_from_id(model_id):
    """Derive a display name from a model ID like 'gpt-5.4-mini' or 'claude-haiku-4-5'."""
    acronyms = {"gpt", "mai", "ai"}
    parts = model_id.split("-")
    # Merge consecutive all-digit parts with dots (e.g. ["4","5"] → "4.5")
    merged = []
    i = 0
    while i < len(parts):
        if parts[i].isdigit():
            num = [parts[i]]
            while i + 1 < len(parts) and parts[i + 1].isdigit():
                i += 1
                num.append(parts[i])
            merged.append(".".join(num))
        else:
            merged.append(parts[i])
        i += 1
    result = []
    for p in merged:
        if p.lower() in acronyms:
            result.append(p.upper())
        elif re.match(r'^\d', p):
            result.append(p)  # version strings stay as-is
        else:
            result.append(p.capitalize())
    return " ".join(result)

result = {}
providers = ["anthropic", "github-copilot"]

for provider in providers:
    print(f"  Processing {provider}...", file=sys.stderr)
    try:
        files = github_list(f"providers/{provider}/models")
    except Exception as e:
        print(f"  Warning: could not list {provider} models: {e}", file=sys.stderr)
        continue

    models = {}
    for f in files:
        if not isinstance(f, dict) or not f.get("name", "").endswith(".toml"):
            continue
        model_id = f["name"][:-5]  # strip .toml
        if DATE_SUFFIX_RE.search(model_id):
            continue  # skip date-suffixed aliases

        download_url = f.get("download_url")
        if not download_url:
            continue

        try:
            toml_text = curl_fetch(download_url)
        except Exception as e:
            print(f"  Warning: could not fetch {model_id}: {e}", file=sys.stderr)
            continue

        cost = parse_toml_cost(toml_text)
        if not cost.get("input") and not cost.get("output"):
            continue  # skip models with no pricing

        name = parse_toml_field(toml_text, "name") or model_name_from_id(model_id)
        models[model_id] = {"name": name, "cost": cost}
        print(f"    {model_id}: {name}", file=sys.stderr)

    result[provider] = {"models": models}
    print(f"  Found {len(models)} models for {provider}", file=sys.stderr)

with open(output_path, "w") as f:
    json.dump(result, f, indent=2)
    f.write("\n")
print(f"Written to {output_path}", file=sys.stderr)
PYEOF

git -C "$REPO_ROOT" add "$OUTPUT"
if git -C "$REPO_ROOT" diff --cached --quiet -- "$OUTPUT"; then
    echo "No changes to models catalog."
else
    git -C "$REPO_ROOT" commit -m "chore: update models catalog from models.dev"
fi
echo "Done."
