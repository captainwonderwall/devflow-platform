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
    git log --oneline -- "$pathspec" | grep -q .
  else
    git log "${tag}..HEAD" --oneline -- "$pathspec" | grep -q .
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

  echo "==> Updating devflow vendor wheel..."
  bash devflow/scripts/update-vendor.sh "v${SDK_NEXT}"
  git add devflow/vendor/
  if ! git diff --cached --quiet -- devflow/vendor/; then
    git commit -m "chore: update devflow-sdk vendor wheel to v${SDK_NEXT}"
    # Re-evaluate devflow release: vendor wheels changed, so devflow needs a
    # new tag and formula update even if it had no prior unreleased commits.
    if ! $DEVFLOW_RELEASE; then
      DEVFLOW_RELEASE=true
      DEVFLOW_NEXT=$(apply_bump "${DEVFLOW_CURRENT:-0.0.0}" "$(semver_bump_for "$DEVFLOW_LAST" "devflow/")")
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
  git subtree push --prefix=homebrew-devflow "$TAP_REMOTE" main
fi

echo ""
echo "==> Release complete."
