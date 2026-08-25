#!/bin/bash
# Run from the root of any devflow plugin repo.
# Bumps pyproject.toml version, commits, tags, and pushes so GitHub Actions
# publishes the release asset.
set -euo pipefail

usage() {
    echo "Usage: $0 [version]"
    echo "  (no args)   Compute next version from Conventional Commits since last tag."
    echo "  version     Semver override, e.g. v1.2.0"
    exit 1
}

[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && usage

# ── Validate we're in a git repo with a pyproject.toml ────────────────────────
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
    echo "ERROR: not inside a git repository." >&2; exit 1
}
PYPROJECT="$REPO_ROOT/pyproject.toml"
[[ -f "$PYPROJECT" ]] || { echo "ERROR: $PYPROJECT not found." >&2; exit 1; }

# ── Read current version ───────────────────────────────────────────────────────
CURRENT_VERSION="$(grep -E '^version[[:space:]]*=' "$PYPROJECT" | head -1 | sed 's/.*=[[:space:]]*"\(.*\)"/\1/')"
[[ -n "$CURRENT_VERSION" ]] || { echo "ERROR: could not read version from $PYPROJECT." >&2; exit 1; }

# ── Compute or validate next version ──────────────────────────────────────────
compute_next_version() {
    local last_tag
    last_tag="$(git tag --list "v*" | sort -V | tail -1)" || true

    local git_range="${last_tag:+${last_tag}..}HEAD"
    local commits
    commits="$(git log $git_range --format="%s%n%b" 2>/dev/null)"

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

    local base="${last_tag#v}"
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
    LAST_TAG="$(git tag --list "v*" | sort -V | tail -1)" || true
    COMMIT_COUNT="$(git log "${LAST_TAG:+${LAST_TAG}..}HEAD" --oneline 2>/dev/null | wc -l | tr -d ' ')"
    VERSION_SOURCE="Computed from ${COMMIT_COUNT} commit(s) since ${LAST_TAG:-the beginning}"
fi

VERSION_BARE="${VERSION#v}"

# Warn on major bump so author updates formula compatibility
NEW_MAJOR="${VERSION_BARE%%.*}"
OLD_MAJOR="${CURRENT_VERSION%%.*}"
if [ "$NEW_MAJOR" -gt "$OLD_MAJOR" ] 2>/dev/null; then
    echo "Major release detected. Before tagging, update your Homebrew formula"
    echo "to constrain the devflow dependency to the new major version."
    echo "  depends_on \"captainwonderwall/devflow/devflow\" # ensure v$NEW_MAJOR compatibility"
    echo ""
fi

# ── Guard: tag must not already exist ─────────────────────────────────────────
if git rev-parse "refs/tags/$VERSION" >/dev/null 2>&1; then
    echo "ERROR: tag $VERSION already exists. Delete it first: git tag -d $VERSION" >&2
    exit 1
fi

# ── Warn on uncommitted changes ───────────────────────────────────────────────
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "WARNING: you have uncommitted changes — they will not be included in the release." >&2
    echo ""
fi

# ── Show summary and confirm ──────────────────────────────────────────────────
SHORT_REV="$(git rev-parse --short HEAD)"
echo "About to release $(basename "$REPO_ROOT") $VERSION"
echo ""
echo "  Current version:  $CURRENT_VERSION"
echo "  New version:      $VERSION_BARE"
echo "  Version source:   $VERSION_SOURCE"
echo "  Tag:              $VERSION → $SHORT_REV"
echo "  Push to:          origin"
echo ""
read -r -p "Proceed? [y/N] " REPLY
echo ""
[[ "$REPLY" =~ ^[Yy]$ ]] || { echo "Aborted. No changes made."; exit 0; }

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
    CLEANUP_MSG="To undo: git tag -d $VERSION && git reset --hard HEAD~1"
else
    CLEANUP_MSG="To undo: git tag -d $VERSION"
fi
trap 'echo ""; echo "ERROR: release step failed. $CLEANUP_MSG"' ERR

if [[ "$SKIP_VERSION_COMMIT" -eq 0 ]]; then
    git add "$PYPROJECT"
    git commit -m "chore: release $VERSION"
fi
git tag "$VERSION"
git push origin HEAD
git push origin "$VERSION"

trap - ERR

echo ""
echo "Released $VERSION."
echo "GitHub Actions will publish the release asset shortly."
