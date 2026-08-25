#!/usr/bin/env bash
# Top-level monorepo release orchestrator.
# Detects unreleased changes per subproject, releases in dependency order,
# and syncs the homebrew tap via git subtree push.
#
# Prerequisites:
#   gh auth status           — GitHub CLI authenticated
#   git remote get-url tap   — tap remote pointing at homebrew-devflow repo
#
# Usage: bash scripts/release.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TAP_REMOTE="${TAP_REMOTE:-tap}"

# ── helpers ──────────────────────────────────────────────────────────────────

latest_tag() {
  # latest_tag <glob>  →  prints the highest semver tag matching glob, or ""
  git tag --list "$1" | sort -V | tail -1
}

has_changes_since() {
  # has_changes_since <tag-or-""> <pathspec>  →  exits 0 if unreleased commits exist
  local tag="$1" pathspec="$2"
  if [[ -z "$tag" ]]; then
    [[ -n "$(git log --oneline -- "$pathspec")" ]]
  else
    [[ -n "$(git log "${tag}..HEAD" --oneline -- "$pathspec")" ]]
  fi
}

semver_bump_for() {
  # semver_bump_for <tag-or-""> <pathspec>  →  prints "major", "minor", or "patch"
  local tag="$1" pathspec="$2"
  local commits
  if [[ -z "$tag" ]]; then
    commits=$(git log --format="%s%n%b" -- "$pathspec" 2>/dev/null)
  else
    commits=$(git log "${tag}..HEAD" --format="%s%n%b" -- "$pathspec" 2>/dev/null)
  fi

  local bump="patch"
  while IFS= read -r line; do
    if [[ "$line" =~ ^[a-z]+(\(.+\))?!: ]] || \
       [[ "$line" == "BREAKING CHANGE"* ]] || \
       [[ "$line" == "BREAKING-CHANGE"* ]]; then
      echo "major"; return
    elif [[ "$line" =~ ^feat(\(.+\))?: ]] && [[ "$bump" != "major" ]]; then
      bump="minor"
    fi
  done <<< "$commits"
  echo "$bump"
}

apply_bump() {
  # apply_bump <bare-version> <bump>  →  prints next bare version (no "v" prefix)
  local version="$1" bump="$2"
  local major minor patch
  IFS='.' read -r major minor patch <<< "${version#v}"
  case "$bump" in
    major) major=$((major+1)); minor=0; patch=0 ;;
    minor) minor=$((minor+1)); patch=0 ;;
    patch) patch=$((patch+1)) ;;
  esac
  echo "${major}.${minor}.${patch}"
}

# ── detect changes ────────────────────────────────────────────────────────────

git fetch --tags --quiet 2>/dev/null \
  || echo "WARNING: could not fetch tags — using local tag state." >&2

# devflow-sdk
SDK_LAST=$(latest_tag "devflow-sdk/v*")
SDK_CURRENT="${SDK_LAST#devflow-sdk/v}"    # bare version, e.g. "0.1.1"
SDK_RELEASE=false; SDK_NEXT=""
if has_changes_since "$SDK_LAST" "devflow-sdk/"; then
  SDK_RELEASE=true
  SDK_NEXT=$(apply_bump "${SDK_CURRENT:-0.0.0}" "$(semver_bump_for "$SDK_LAST" "devflow-sdk/")")
fi

# devflow (released as one unit via devflow/v* tag, one formula)
DEVFLOW_LAST=$(latest_tag "devflow/v*")
DEVFLOW_CURRENT="${DEVFLOW_LAST#devflow/v}"
DEVFLOW_RELEASE=false; DEVFLOW_NEXT=""
if has_changes_since "$DEVFLOW_LAST" "devflow/"; then
  DEVFLOW_RELEASE=true
  DEVFLOW_NEXT=$(apply_bump "${DEVFLOW_CURRENT:-0.0.0}" "$(semver_bump_for "$DEVFLOW_LAST" "devflow/")")
fi

# devflow-plugin-scaffold
SCAFFOLD_LAST=$(latest_tag "devflow-plugin-scaffold/v*")
SCAFFOLD_CURRENT="${SCAFFOLD_LAST#devflow-plugin-scaffold/v}"
if [[ -z "$SCAFFOLD_CURRENT" ]]; then
  SCAFFOLD_CURRENT=$(cat devflow-plugin-scaffold/VERSION 2>/dev/null || echo "0.0.0")
fi
SCAFFOLD_RELEASE=false; SCAFFOLD_NEXT=""
if has_changes_since "$SCAFFOLD_LAST" "devflow-plugin-scaffold/"; then
  SCAFFOLD_RELEASE=true
  SCAFFOLD_NEXT=$(apply_bump "$SCAFFOLD_CURRENT" "$(semver_bump_for "$SCAFFOLD_LAST" "devflow-plugin-scaffold/")")
fi

# ── preflight checks ─────────────────────────────────────────────────────────

if $DEVFLOW_RELEASE && ! git remote get-url "$TAP_REMOTE" &>/dev/null; then
  echo "ERROR: remote '$TAP_REMOTE' not found. Add it before releasing devflow:" >&2
  echo "  git remote add $TAP_REMOTE https://github.com/captainwonderwall/homebrew-devflow.git" >&2
  exit 1
fi

# ── summary + confirm ─────────────────────────────────────────────────────────

if ! $SDK_RELEASE && ! $DEVFLOW_RELEASE && ! $SCAFFOLD_RELEASE; then
  echo "Nothing to release."
  exit 0
fi

echo "==> Pending releases:"
$SDK_RELEASE       && echo "  devflow-sdk:               ${SDK_LAST:-none} → devflow-sdk/v${SDK_NEXT}"
$DEVFLOW_RELEASE   && echo "  devflow:                   ${DEVFLOW_LAST:-none} → devflow/v${DEVFLOW_NEXT}"
$SCAFFOLD_RELEASE  && echo "  devflow-plugin-scaffold:   ${SCAFFOLD_LAST:-none} → devflow-plugin-scaffold/v${SCAFFOLD_NEXT}"
echo ""
read -rp "Proceed? [y/N] " REPLY
[[ "$REPLY" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }
export RELEASE_AUTO_CONFIRM=1
echo ""

# ── release devflow-sdk ───────────────────────────────────────────────────────

if $SDK_RELEASE; then
  echo "==> Releasing devflow-sdk v${SDK_NEXT}..."
  (cd devflow-sdk && bash scripts/release.sh "v${SDK_NEXT}")

  echo "==> Updating devflow-sdk resource block in Homebrew formula..."
  WHEEL_FILENAME="devflow_sdk-${SDK_NEXT}-py3-none-any.whl"
  WHEEL_URL="https://github.com/captainwonderwall/devflow-platform/releases/download/devflow-sdk%2Fv${SDK_NEXT}/${WHEEL_FILENAME}"
  TMPWHL="${TMPDIR:-/tmp}/devflow_sdk_update_${SDK_NEXT}.whl"
  gh release download "devflow-sdk/v${SDK_NEXT}" \
    --repo captainwonderwall/devflow-platform \
    --pattern "${WHEEL_FILENAME}" \
    --output "$TMPWHL" \
    --clobber
  WHEEL_SHA256=$(shasum -a 256 "$TMPWHL" | awk '{print $1}')
  rm -f "$TMPWHL"

  FORMULA="homebrew-devflow/Formula/devflow.rb"
  python3 - "$FORMULA" "$WHEEL_URL" "$WHEEL_SHA256" <<'PYEOF'
import sys, re
path, url, sha256 = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path) as f:
    content = f.read()
content = re.sub(
    r'(resource "devflow-sdk" do\s+url ")[^"]*(")',
    lambda m: m.group(1) + url + m.group(2),
    content,
)
content = re.sub(
    r'(resource "devflow-sdk" do.*?sha256 ")[^"]*(")',
    lambda m: m.group(1) + sha256 + m.group(2),
    content,
    flags=re.DOTALL,
)
with open(path, "w") as f:
    f.write(content)
PYEOF

  git add homebrew-devflow/
  if ! git diff --cached --quiet -- homebrew-devflow/; then
    git commit -m "chore: update devflow-sdk resource to v${SDK_NEXT} in homebrew formula"
    if ! $DEVFLOW_RELEASE; then
      DEVFLOW_RELEASE=true
      DEVFLOW_NEXT=$(apply_bump "${DEVFLOW_CURRENT:-0.0.0}" "patch")
    fi
  fi
fi

# ── release devflow ───────────────────────────────────────────────────────────

if $DEVFLOW_RELEASE; then
  echo "==> Releasing devflow v${DEVFLOW_NEXT}..."
  # devflow/scripts/release.sh in single-tool mode; version override bypasses
  # its internal detection. MONOREPO_MODE skips tap commit/push.
  (cd devflow && MONOREPO_MODE=1 bash scripts/release.sh devflow "v${DEVFLOW_NEXT}")

  # Stage any formula changes made by the above and commit to the monorepo
  git add homebrew-devflow/
  if ! git diff --cached --quiet -- homebrew-devflow/; then
    git commit -m "chore: update homebrew formula for devflow/v${DEVFLOW_NEXT}"
  fi
fi

# ── release devflow-plugin-scaffold ──────────────────────────────────────────

if $SCAFFOLD_RELEASE; then
  echo "==> Releasing devflow-plugin-scaffold v${SCAFFOLD_NEXT}..."
  echo "${SCAFFOLD_NEXT}" > devflow-plugin-scaffold/VERSION
  git add devflow-plugin-scaffold/VERSION
  git commit -m "chore: release devflow-plugin-scaffold/v${SCAFFOLD_NEXT}"
  git tag "devflow-plugin-scaffold/v${SCAFFOLD_NEXT}"
  git push origin HEAD "devflow-plugin-scaffold/v${SCAFFOLD_NEXT}"
fi

# ── sync homebrew tap ─────────────────────────────────────────────────────────

if $DEVFLOW_RELEASE; then
  echo "==> Syncing homebrew tap via git subtree push..."
  TAP_BRANCH="release/devflow-v${DEVFLOW_NEXT}"
  git subtree push --prefix=homebrew-devflow "$TAP_REMOTE" "$TAP_BRANCH"
  echo "==> Opening PR to homebrew tap..."
  gh pr create \
    --repo captainwonderwall/homebrew-devflow \
    --base main \
    --head "$TAP_BRANCH" \
    --title "chore: update formula for devflow/v${DEVFLOW_NEXT}" \
    --body "Automated formula update from devflow-platform release script for devflow v${DEVFLOW_NEXT}."
fi

# ── push commits and tags ─────────────────────────────────────────────────────

echo "==> Pushing commits and tags to origin..."
git push origin main
if $DEVFLOW_RELEASE; then
  git push origin "devflow/v${DEVFLOW_NEXT}"
fi

echo ""
echo "==> Release complete."
