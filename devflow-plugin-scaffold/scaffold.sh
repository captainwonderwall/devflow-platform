#!/bin/bash
# scaffold.sh — generate a ready-to-publish devflow plugin repo
# Usage: bash scaffold.sh <plugin-name>
# Example: bash scaffold.sh acme-format
set -euo pipefail

PLUGIN_NAME="${1:?Usage: scaffold.sh <plugin-name>  (e.g. acme-format)}"

if ! printf '%s' "$PLUGIN_NAME" | grep -qE '^[a-z][a-z0-9-]*$'; then
    printf 'ERROR: plugin-name must start with a lowercase letter and contain only lowercase letters, digits, and hyphens.\n' >&2
    exit 1
fi

if [ -e "$PLUGIN_NAME" ]; then
    printf 'ERROR: "%s" already exists.\n' "$PLUGIN_NAME" >&2
    exit 1
fi

# ── Derive identifiers ────────────────────────────────────────────────────────
MODULE_NAME="${PLUGIN_NAME//-/_}"
FIRST_PART="${PLUGIN_NAME%%-*}"
FIRST_UPPER="$(printf '%s' "${FIRST_PART:0:1}" | tr '[:lower:]' '[:upper:]')${FIRST_PART:1}"
CLASS_NAME="${FIRST_UPPER}Plugin"
DISPLAY_NAME="$(printf '%s' "$PLUGIN_NAME" | tr '-' '\n' \
    | awk '{print toupper(substr($0,1,1)) tolower(substr($0,2))}' \
    | tr '\n' ' ' | sed 's/ $//')"

# Derive Ruby formula class name: DevflowPlugin<PascalCase of plugin-name>
FORMULA_CLASS_NAME="DevflowPlugin$(printf '%s' "$PLUGIN_NAME" | tr '-' '\n' | \
    awk '{print toupper(substr($0,1,1)) tolower(substr($0,2))}' | tr -d '\n')"

mkdir -p "$PLUGIN_NAME/tests" "$PLUGIN_NAME/.github/workflows" "$PLUGIN_NAME/scripts" "$PLUGIN_NAME/Formula"

# ── Plugin stub ───────────────────────────────────────────────────────────────
cat > "$PLUGIN_NAME/${MODULE_NAME}.py" << 'PYEOF'
from devflow_sdk.draft_pr_plugin import DraftPrPlugin


class __CLASS_NAME__(DraftPrPlugin):
    name = "__DISPLAY_NAME__"

    def get_questions(self, data: dict) -> list[dict]:
        return []

    def build_prompt(self, data: dict, user_inputs: dict) -> str:
        # Return an AI prompt string. draft-pr passes this to run_ai_prompt.
        # data keys: git_log, diff_stat, changed_files, branch, is_fix, ...
        # user_inputs keys: jira_ticket, github_issue, issue_type, customer_visible, ...
        # The JSON keys you ask for here are what build_body receives in ai_result.
        return (
            "Output ONLY a JSON object with keys title and description:\n"
            + data["git_log"]
        )

    def build_body(self, ai_result: dict, user_inputs: dict) -> str:
        # Render the PR body markdown from ai_result.
        return f"## {ai_result['title']}\n\n{ai_result['description']}\n"
PYEOF
sed -i.bak \
    -e "s/__CLASS_NAME__/${CLASS_NAME}/g" \
    -e "s/__DISPLAY_NAME__/${DISPLAY_NAME}/g" \
    "$PLUGIN_NAME/${MODULE_NAME}.py" && rm "$PLUGIN_NAME/${MODULE_NAME}.py.bak"

# ── Generated tests ───────────────────────────────────────────────────────────
cat > "$PLUGIN_NAME/tests/test_${MODULE_NAME}.py" << 'PYEOF'
from __MODULE_NAME__ import __CLASS_NAME__


def test_build_body_contains_title():
    plugin = __CLASS_NAME__()
    ai_result = {"title": "Fix login", "description": "Fixes the login flow"}
    body = plugin.build_body(ai_result, user_inputs={})
    assert "Fix login" in body


def test_build_body_contains_description():
    plugin = __CLASS_NAME__()
    ai_result = {"title": "Fix login", "description": "Fixes the login flow"}
    body = plugin.build_body(ai_result, user_inputs={})
    assert "Fixes the login flow" in body


def test_build_prompt_returns_string():
    plugin = __CLASS_NAME__()
    data = {
        "git_log": "abc123 Fix auth",
        "diff_stat": "1 file changed",
        "changed_files": ["src/auth.py"],
    }
    prompt = plugin.build_prompt(data, user_inputs={})
    assert isinstance(prompt, str)
    assert len(prompt) > 0


def test_get_questions_returns_list():
    plugin = __CLASS_NAME__()
    result = plugin.get_questions({})
    assert isinstance(result, list)
PYEOF
sed -i.bak \
    -e "s/__MODULE_NAME__/${MODULE_NAME}/g" \
    -e "s/__CLASS_NAME__/${CLASS_NAME}/g" \
    "$PLUGIN_NAME/tests/test_${MODULE_NAME}.py" && rm "$PLUGIN_NAME/tests/test_${MODULE_NAME}.py.bak"

# ── pyproject.toml ────────────────────────────────────────────────────────────
cat > "$PLUGIN_NAME/pyproject.toml" << EOF
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "${PLUGIN_NAME}"
version = "0.1.0"
requires-python = ">=3.9"

[project.optional-dependencies]
dev = [
    "devflow-sdk>=0.1.0,<1.0",
    "pytest>=7.0",
]
EOF

# ── install.sh ────────────────────────────────────────────────────────────────
cat > "$PLUGIN_NAME/install.sh" << EOF
#!/bin/bash
# Development convenience install — for Homebrew distribution use Formula/ instead.
set -euo pipefail
PLUGIN_DIR="\$(cd "\$(dirname "\$0")" && pwd)"
devflow-plugin register "${PLUGIN_NAME}" "\$PLUGIN_DIR/${MODULE_NAME}.py"
echo "Installed ${PLUGIN_NAME}."
EOF
chmod +x "$PLUGIN_NAME/install.sh"

# ── uninstall.sh ──────────────────────────────────────────────────────────────
cat > "$PLUGIN_NAME/uninstall.sh" << EOF
#!/bin/bash
set -euo pipefail
devflow-plugin unregister "${PLUGIN_NAME}"
echo "Uninstalled ${PLUGIN_NAME}."
EOF
chmod +x "$PLUGIN_NAME/uninstall.sh"

# ── Homebrew formula template ────────────────────────────────────────────────
cat > "$PLUGIN_NAME/Formula/devflow-plugin-${PLUGIN_NAME}.rb" << 'RBEOF'
class __FORMULA_CLASS_NAME__ < Formula
  desc "devflow plugin: __DISPLAY_NAME__"
  homepage "<your-plugin-homepage>"
  url "<release-url-to-__MODULE_NAME__.py>"
  sha256 "<sha256-of-__MODULE_NAME__.py>"
  version "0.1.0"

  depends_on "captainwonderwall/devflow/devflow"

  def install
    lib.install "__MODULE_NAME__.py"
  end

  def post_install
    system "#{HOMEBREW_PREFIX}/bin/devflow-plugin",
           "register", "__PLUGIN_NAME__",
           "#{opt_lib}/__MODULE_NAME__.py",
           "--formula", "<your-tap>/__PLUGIN_NAME__"
  end

  # To unregister before uninstalling: devflow-plugin unregister __PLUGIN_NAME__

  test do
    system "#{HOMEBREW_PREFIX}/bin/devflow-plugin", "list"
  end
end
RBEOF
sed -i.bak \
    -e "s/__FORMULA_CLASS_NAME__/${FORMULA_CLASS_NAME}/g" \
    -e "s/__DISPLAY_NAME__/${DISPLAY_NAME}/g" \
    -e "s/__MODULE_NAME__/${MODULE_NAME}/g" \
    -e "s/__PLUGIN_NAME__/${PLUGIN_NAME}/g" \
    "$PLUGIN_NAME/Formula/devflow-plugin-${PLUGIN_NAME}.rb" && rm "$PLUGIN_NAME/Formula/devflow-plugin-${PLUGIN_NAME}.rb.bak"

# ── GitHub Actions release workflow ───────────────────────────────────────────
# Pass github.ref_name through an env var to avoid script injection.
cat > "$PLUGIN_NAME/.github/workflows/release.yml" << 'YAMEOF'
name: Release

on:
  push:
    tags:
      - "v*"

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4

      - name: Create GitHub Release
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          TAG: ${{ github.ref_name }}
        run: |
          gh release create "$TAG" \
            --title "$TAG" \
            --generate-notes \
            __MODULE_NAME__.py
YAMEOF
sed -i.bak "s/__MODULE_NAME__/${MODULE_NAME}/g" "$PLUGIN_NAME/.github/workflows/release.yml" \
    && rm "$PLUGIN_NAME/.github/workflows/release.yml.bak"

# ── Generated README ──────────────────────────────────────────────────────────
cat > "$PLUGIN_NAME/README.md" << EOF
# ${PLUGIN_NAME}

A [devflow](https://github.com/captainwonderwall/devflow) plugin for \`draft-pr\`.

## Install

\`\`\`bash
bash install.sh
\`\`\`

## Uninstall

\`\`\`bash
bash uninstall.sh
\`\`\`

## Develop

\`\`\`bash
# Install dev dependencies (or point PYTHONPATH at a local devflow-sdk clone)
pip install devflow-sdk pytest

# Run tests — no AI required
PYTHONPATH=. pytest tests/
\`\`\`

## Publish a release

1. Fill in \`build_prompt\` and \`build_body\` in \`${MODULE_NAME}.py\`.
2. Run tests: \`PYTHONPATH=. pytest tests/\`.
3. Commit your changes, then run:
   \`\`\`bash
   bash scripts/release.sh
   \`\`\`
   This bumps the version, tags, and pushes. GitHub Actions creates a release and attaches \`${MODULE_NAME}.py\` as an asset.
EOF

# ── scripts/release.sh ───────────────────────────────────────────────────────
cat > "$PLUGIN_NAME/scripts/release.sh" << 'SCRIPTEOF'
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
SCRIPTEOF
chmod +x "$PLUGIN_NAME/scripts/release.sh"

# ── .gitignore ────────────────────────────────────────────────────────────────
cat > "$PLUGIN_NAME/.gitignore" << 'EOF'
__pycache__/
*.pyc
*.pyo
.pytest_cache/
*.egg-info/
dist/
build/
EOF

printf '\nCreated scaffold at ./%s/\n' "$PLUGIN_NAME"
printf '\nNext steps:\n'
printf '  cd %s\n' "$PLUGIN_NAME"
printf '  PYTHONPATH=. pytest tests/   # should pass\n'
printf '  # Fill in build_prompt and build_body in %s.py\n' "$MODULE_NAME"
printf '  # Push to GitHub and tag: git tag v0.1.0 && git push --tags\n'
