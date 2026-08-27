#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT="$REPO_ROOT/devflow-sdk/devflow_sdk/config/wizard/tools/models_catalog.json"

echo "==> Downloading models catalog from models.dev..."
TMP=$(mktemp)
curl -fsSL --max-time 30 "https://models.dev/api.json" -o "$TMP"

echo "==> Extracting relevant providers..."
python3 - "$TMP" "$OUTPUT" <<'PYEOF'
import json, sys
src, dst = sys.argv[1], sys.argv[2]
with open(src) as f:
    data = json.load(f)
relevant = {k: data[k] for k in ("anthropic", "github-copilot") if k in data}
with open(dst, "w") as f:
    json.dump(relevant, f, indent=2)
    f.write("\n")
PYEOF
rm -f "$TMP"

git -C "$REPO_ROOT" add "$OUTPUT"
if git -C "$REPO_ROOT" diff --cached --quiet -- "$OUTPUT"; then
    echo "No changes to models catalog."
else
    git -C "$REPO_ROOT" commit -m "chore: update models catalog from models.dev"
fi
echo "Done."
