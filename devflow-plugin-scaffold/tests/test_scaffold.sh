#!/bin/bash
# Tests for scaffold.sh — runs in bash, no external test framework needed.
set -euo pipefail

SCAFFOLD="$(cd "$(dirname "$0")/.." && pwd)/scaffold.sh"
DEVFLOW_SDK="${DEVFLOW_SDK:-}"
WORK="$(mktemp -d -p "${TMPDIR:-/tmp}")"
trap "rm -rf '$WORK'" EXIT

PASS=0; FAIL=0

ok()   { PASS=$((PASS + 1)); }
fail() { echo "FAIL: $1" >&2; FAIL=$((FAIL + 1)); }

file_exists() { [ -f "$1" ] && ok || fail "expected file: $1"; }
has_content() { grep -q "$2" "$1" 2>/dev/null && ok || fail "expected '$2' in $1"; }
exits_nonzero() {
    if ! eval "$1" >/dev/null 2>&1; then ok
    else fail "expected nonzero exit from: $1"; fi
}

# ── basic: acme-format ───────────────────────────────────────────────────────
(cd "$WORK" && bash "$SCAFFOLD" acme-format)
D="$WORK/acme-format"

file_exists "$D/acme_format.py"
file_exists "$D/tests/test_acme_format.py"
file_exists "$D/pyproject.toml"
file_exists "$D/install.sh"
file_exists "$D/uninstall.sh"
file_exists "$D/.github/workflows/release.yml"
file_exists "$D/README.md"
file_exists "$D/.gitignore"

has_content "$D/acme_format.py"                   "class AcmePlugin"
has_content "$D/acme_format.py"                   'name = "Acme Format"'
has_content "$D/acme_format.py"                   "from devflow_sdk.draft_pr_plugin import DraftPrPlugin"
has_content "$D/acme_format.py"                   "class AcmePlugin(DraftPrPlugin)"
has_content "$D/tests/test_acme_format.py"        "from acme_format import AcmePlugin"
has_content "$D/tests/test_acme_format.py"        "def test_build_body_contains_title"
has_content "$D/tests/test_acme_format.py"        "def test_build_prompt_returns_string"
has_content "$D/pyproject.toml"                   "devflow-sdk>=0.1.0,<1.0"
has_content "$D/pyproject.toml"                   "pytest>=7.0"
has_content "$D/.github/workflows/release.yml"    "acme_format.py"
has_content "$D/.github/workflows/release.yml"    'GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}'
has_content "$D/.github/workflows/release.yml"    'TAG: ${{ github.ref_name }}'
has_content "$D/.github/workflows/release.yml"    '"$TAG"'
has_content "$D/scripts/release.sh"               "Major release detected"
has_content "$D/install.sh"                       "devflow-plugin"
has_content "$D/install.sh"                       "register"
has_content "$D/install.sh"                       "acme-format"
has_content "$D/uninstall.sh"                     "devflow-plugin"
has_content "$D/uninstall.sh"                     "unregister"
has_content "$D/uninstall.sh"                     "acme-format"
file_exists "$D/Formula/devflow-plugin-acme-format.rb"
has_content "$D/Formula/devflow-plugin-acme-format.rb"  "DevflowPluginAcmeFormat"
has_content "$D/Formula/devflow-plugin-acme-format.rb"  "depends_on"
has_content "$D/Formula/devflow-plugin-acme-format.rb"  "devflow-plugin"
has_content "$D/Formula/devflow-plugin-acme-format.rb"  "register"
has_content "$D/Formula/devflow-plugin-acme-format.rb"  "post_install"

# ── single-word name ──────────────────────────────────────────────────────────
(cd "$WORK" && bash "$SCAFFOLD" acme)
file_exists "$WORK/acme/acme.py"
has_content "$WORK/acme/acme.py" "class AcmePlugin"
has_content "$WORK/acme/acme.py" 'name = "Acme"'
file_exists "$WORK/acme/tests/test_acme.py"
has_content "$WORK/acme/tests/test_acme.py" "from acme import AcmePlugin"

# ── multi-hyphen name ─────────────────────────────────────────────────────────
(cd "$WORK" && bash "$SCAFFOLD" my-org-format)
file_exists "$WORK/my-org-format/my_org_format.py"
has_content "$WORK/my-org-format/my_org_format.py" "class MyPlugin"
has_content "$WORK/my-org-format/my_org_format.py" 'name = "My Org Format"'

# ── error: no argument ────────────────────────────────────────────────────────
exits_nonzero "bash '$SCAFFOLD'"

# ── error: target already exists ─────────────────────────────────────────────
mkdir -p "$WORK/already-exists"
exits_nonzero "cd '$WORK' && bash '$SCAFFOLD' already-exists"

# ── error: invalid name (uppercase) ──────────────────────────────────────────
exits_nonzero "cd '$WORK' && bash '$SCAFFOLD' Invalid-Name"

# ── error: starts with digit ──────────────────────────────────────────────────
exits_nonzero "cd '$WORK' && bash '$SCAFFOLD' 123bad"

# ── integration: generated plugin tests pass ──────────────────────────────────
# The generated plugin's stubs are functional — its own test suite should pass.
if [ -z "$DEVFLOW_SDK" ] || ! python3 -c "import sys; sys.path.insert(0, '$DEVFLOW_SDK'); import devflow_sdk" 2>/dev/null; then
    echo "SKIP: integration test skipped (set DEVFLOW_SDK=/path/to/devflow-sdk to enable)"
    ok
else
    if PYTHONPATH="$DEVFLOW_SDK:$D" python3 -m pytest "$D/tests/" -q 2>&1; then
        ok
    else
        fail "generated tests did not pass for acme-format (check DEVFLOW_SDK=$DEVFLOW_SDK)"
    fi
fi

# ── summary ───────────────────────────────────────────────────────────────────
echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
