#!/bin/bash
# Downloads devflow_sdk wheel from GitHub Releases and updates vendor/.
# Usage: bash scripts/update-vendor.sh [version]
#   version: bare or v-prefixed semver, e.g. v0.2.0 or 0.2.0
#            Defaults to the latest devflow-sdk/v* tag.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$REPO_ROOT/vendor"
TAG="${1:-}"

if [[ -z "$TAG" ]]; then
  TAG=$(git tag --list "devflow-sdk/v*" | sort -V | tail -1)
  [[ -n "$TAG" ]] || { echo "ERROR: no devflow-sdk/v* tags found. Pass a version explicitly." >&2; exit 1; }
  TAG="${TAG#devflow-sdk/}"  # strip prefix → "v0.2.0"
fi

[[ "$TAG" == v* ]] || TAG="v${TAG}"

echo "Downloading devflow_sdk wheel for ${TAG}..."
rm -f "$VENDOR"/devflow_sdk-*.whl
gh release download "devflow-sdk/${TAG}" \
  --repo captainwonderwall/devflow-platform \
  --pattern "devflow_sdk-*.whl" \
  --dir "$VENDOR" \
  --clobber
echo "devflow_sdk wheel updated in $VENDOR"
