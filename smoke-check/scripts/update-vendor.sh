#!/bin/bash
# Downloads wheel files for this plugin's runtime deps into vendor/.
# Run after changing [project.dependencies] in pyproject.toml.
# Commit the resulting vendor/ changes.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$REPO_ROOT/vendor"
mkdir -p "$VENDOR"

deps=$(python3 -c "
import tomllib, sys
with open(sys.argv[1], 'rb') as f:
    data = tomllib.load(f)
deps = data.get('project', {}).get('dependencies', [])
if deps:
    print(' '.join(deps))
" "$REPO_ROOT/pyproject.toml")

if [[ -z "$deps" ]]; then
    echo "No runtime dependencies declared — vendor/ stays empty."
    exit 0
fi

rm -f "$VENDOR"/*.whl
uv pip download --no-deps --output-dir "$VENDOR" $deps
echo "vendor/ updated."
