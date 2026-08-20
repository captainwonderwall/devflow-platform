#!/bin/bash
# Run from the root of any devflow plugin repo.
# Bumps pyproject.toml version, commits, tags, and pushes so GitHub Actions
# publishes the release asset.
set -euo pipefail
RELEASE_AUTO_CONFIRM="${RELEASE_AUTO_CONFIRM:-0}"

usage() {
    echo "Usage: $0 [version]"
    echo "  (no args)   Compute next version from Conventional Commits since last tag."
    echo "  version     Semver override, e.g. v1.2.0"
    exit 1
}

[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && usage

# ── Validate we're in a git repo with a pyproject.toml ────────────────────────
git rev-parse --show-toplevel >/dev/null 2>&1 || {
    echo "ERROR: not inside a git repository." >&2; exit 1
}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYPROJECT="$PROJECT_DIR/pyproject.toml"
[[ -f "$PYPROJECT" ]] || { echo "ERROR: $PYPROJECT not found." >&2; exit 1; }

# ── Read current version ───────────────────────────────────────────────────────
CURRENT_VERSION="$(grep -E '^version[[:space:]]*=' "$PYPROJECT" | head -1 | sed 's/.*=[[:space:]]*"\(.*\)"/\1/')"
[[ -n "$CURRENT_VERSION" ]] || { echo "ERROR: could not read version from $PYPROJECT." >&2; exit 1; }

# ── Compute or validate next version ──────────────────────────────────────────
compute_next_version() {
    local last_tag
    last_tag="$(git tag --list "devflow-sdk/v*" | sort -V | tail -1)" || true

    local git_range="${last_tag:+${last_tag}..}HEAD"
    local commits
    commits="$(git log $git_range --format="%s%n%b" -- . 2>/dev/null)"

    if [[ -z "$commits" ]]; then
        echo "ERROR: no commits since ${last_tag:-the beginning}. Nothing to release." >&2
        exit 1
    fi

    local bump="patch"
    while IFS= read -r line; do
        if [[ "$line" =~ ^[a-z]+(\(.+\))?!: ]] || [[ "$line" == "BREAKING CHANGE"* ]] || [[ "$line" == "BREAKING-CHANGE"* ]]; then
            bump="major"; break
        elif [[ "$line" =~ ^feat(\(.+\))?: ]] && [[ "$bump" != "major" ]]; then
            bump="minor"
        fi
    done <<< "$commits"

    local base="${last_tag#devflow-sdk/v}"
    local major minor patch
    IFS='.' read -r major minor patch <<< "${base:-0.0.0}"

    case "$bump" in
        major) major=$((major + 1)); minor=0; patch=0 ;;
        minor) minor=$((minor + 1)); patch=0 ;;
        patch) patch=$((patch + 1)) ;;
    esac

    echo "v${major}.${minor}.${patch}"
}

if [[ $# -ge 1 ]]; then
    VERSION="$1"
    [[ "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
        echo "ERROR: version must be in format v1.2.3 (got: $VERSION)" >&2; exit 1
    }
    VERSION_SOURCE="Override: specified manually"
else
    git fetch --tags --quiet 2>/dev/null || echo "WARNING: could not fetch tags — using local tag state." >&2
    VERSION="$(compute_next_version)"
    LAST_TAG="$(git tag --list "devflow-sdk/v*" | sort -V | tail -1)" || true
    COMMIT_COUNT="$(git log "${LAST_TAG:+${LAST_TAG}..}HEAD" --oneline -- . 2>/dev/null | wc -l | tr -d ' ')"
    VERSION_SOURCE="Computed from ${COMMIT_COUNT} commit(s) since ${LAST_TAG:-the beginning}"
fi

VERSION_BARE="${VERSION#v}"

# ── Guard: tag must not already exist ─────────────────────────────────────────
if git rev-parse "refs/tags/devflow-sdk/$VERSION" >/dev/null 2>&1; then
    echo "ERROR: tag devflow-sdk/$VERSION already exists. Delete it first: git tag -d devflow-sdk/$VERSION" >&2
    exit 1
fi

# ── Warn on uncommitted changes ───────────────────────────────────────────────
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "WARNING: you have uncommitted changes — they will not be included in the release." >&2
    echo ""
fi

# ── Show summary and confirm ──────────────────────────────────────────────────
SHORT_REV="$(git rev-parse --short HEAD)"
echo "About to release $(basename "$PROJECT_DIR") $VERSION"
echo ""
echo "  Current version:  $CURRENT_VERSION"
echo "  New version:      $VERSION_BARE"
echo "  Version source:   $VERSION_SOURCE"
echo "  Tag:              $VERSION → $SHORT_REV"
echo "  Push to:          origin"
echo ""
if [[ "$RELEASE_AUTO_CONFIRM" != "1" ]]; then
    read -r -p "Proceed? [y/N] " REPLY
    echo ""
    [[ "$REPLY" =~ ^[Yy]$ ]] || { echo "Aborted. No changes made."; exit 0; }
fi

# ── Bump version in pyproject.toml ───────────────────────────────────────────
if [[ "$CURRENT_VERSION" == "$VERSION_BARE" ]]; then
    echo "pyproject.toml already at $VERSION_BARE — skipping version bump commit."
    SKIP_VERSION_COMMIT=1
else
    sed -i '' "s/^version[[:space:]]*=[[:space:]]*\"$CURRENT_VERSION\"/version = \"$VERSION_BARE\"/" "$PYPROJECT"

    if git diff --quiet "$PYPROJECT"; then
        echo "ERROR: pyproject.toml was not modified — version line may not match expected format." >&2
        exit 1
    fi
    SKIP_VERSION_COMMIT=0
fi

# ── Commit, tag, push ─────────────────────────────────────────────────────────
if [[ "$SKIP_VERSION_COMMIT" -eq 0 ]]; then
    CLEANUP_MSG="To undo: git tag -d devflow-sdk/$VERSION && git reset --hard HEAD~1"
else
    CLEANUP_MSG="To undo: git tag -d devflow-sdk/$VERSION"
fi
trap 'echo ""; echo "ERROR: release step failed. $CLEANUP_MSG"' ERR

if [[ "$SKIP_VERSION_COMMIT" -eq 0 ]]; then
    git add "$PYPROJECT"
    git commit -m "chore: release devflow-sdk/$VERSION"
fi
git tag "devflow-sdk/$VERSION"
git push origin HEAD
git push origin "devflow-sdk/$VERSION"

# Build wheel and attach to GitHub Release
echo ""
echo "Building wheel..."
(cd "$PROJECT_DIR" && uv build --wheel)
WHL=$(ls "$PROJECT_DIR/dist/devflow_sdk-${VERSION_BARE}-"*.whl | head -1)
[[ -f "$WHL" ]] || { echo "ERROR: wheel not found in $PROJECT_DIR/dist/" >&2; exit 1; }

echo "Creating GitHub Release devflow-sdk/$VERSION..."
gh release create "devflow-sdk/$VERSION" \
  --repo captainwonderwall/devflow-platform \
  --title "devflow-sdk $VERSION" \
  "$WHL"

trap - ERR

echo ""
echo "Released devflow-sdk/$VERSION."
echo "Wheel attached to GitHub Release."
