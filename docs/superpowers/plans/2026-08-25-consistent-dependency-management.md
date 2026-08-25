# Consistent Dependency Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate committed wheel files from the platform, replace them with Homebrew resource blocks and uv-based dev tooling, and update the scaffold to generate plugin repos that work out of the box for dev, CI, and Homebrew runtime.

**Architecture:** Three parallel tracks executed sequentially for safety: (1) update the Homebrew formula to use resource blocks before deleting the vendor wheels it currently reads; (2) add `justfile` as the standard command interface across the monorepo; (3) update `scaffold.sh` TDD-first — add failing assertions in `test_scaffold.sh`, then implement the scaffold changes to make them pass.

**Tech Stack:** bash, Python 3.11+ (tomllib stdlib), uv, just, Homebrew Ruby, GitHub Actions YAML

**Spec:** `docs/superpowers/specs/2026-08-25-consistent-dependency-management-design.md`

**Models:** Implementation — Haiku. Review checkpoints — claude-sonnet-4-6.

## Global Constraints

- Python ≥ 3.11 required (tomllib is stdlib — no extra import needed)
- uv is the only Python tool used in CI and locally (already in CI via `astral-sh/setup-uv@v4`)
- `just` is for local dev only — never referenced in CI YAML
- devflow-sdk git dep pin: `devflow-sdk @ git+https://github.com/captainwonderwall/devflow-platform@devflow-sdk/v0.3.2#subdirectory=devflow-sdk`
- All pytest invocations: `uv run --extra dev pytest` (plugin/sdk context) or `uv run --no-project pytest` (devflow tools context)
- Never `pip install` globally; never commit `.venv/`; never commit wheels to devflow-sdk or plugin repos

---

## File Map

**Create:**
- `justfile` — root monorepo command runner
- `devflow-sdk/justfile` — SDK dev commands

**Modify:**
- `homebrew-devflow/Formula/devflow.rb` — remove vendor install loop; add 4 resource blocks
- `.github/workflows/ci.yml` — simplify devflow-tests; add DEVFLOW_SDK to scaffold-tests
- `scripts/release.sh` — lines 137–149: replace vendor update with formula resource block update
- `devflow-plugin-scaffold/scaffold.sh` — update 4 existing heredocs; add 5 new heredoc blocks
- `devflow-plugin-scaffold/tests/test_scaffold.sh` — add 15 new assertions

**Delete:**
- `devflow/vendor/devflow_sdk-0.3.2-py3-none-any.whl`
- `devflow/vendor/questionary-2.1.1-py3-none-any.whl`
- `devflow/vendor/prompt_toolkit-3.0.53-py3-none-any.whl`
- `devflow/vendor/wcwidth-0.8.2-py3-none-any.whl`
- `devflow/vendor/` (directory)
- `devflow/conftest.py`
- `devflow/scripts/update-vendor.sh`

---

## Task 1: Update Homebrew formula with resource blocks

> **Do this BEFORE Task 2.** The sha256 values are computed from the vendor/ wheel files that Task 2 deletes.

**Files:**
- Modify: `homebrew-devflow/Formula/devflow.rb`

**Interfaces:**
- Produces: a formula that installs devflow-sdk, questionary, prompt_toolkit, wcwidth via `resource` blocks instead of vendor/ wheels. The `install` method structure (PYTHONPATH shims) is unchanged.

- [ ] **Step 1: Compute sha256 for each existing vendor wheel**

Run from the repo root:
```bash
shasum -a 256 devflow/vendor/devflow_sdk-0.3.2-py3-none-any.whl
shasum -a 256 devflow/vendor/questionary-2.1.1-py3-none-any.whl
shasum -a 256 devflow/vendor/prompt_toolkit-3.0.53-py3-none-any.whl
shasum -a 256 devflow/vendor/wcwidth-0.8.2-py3-none-any.whl
```
Record the four 64-character hex strings. These are the `sha256` values for the resource blocks.

- [ ] **Step 2: Find the canonical PyPI download URLs**

Run:
```bash
python3 - <<'EOF'
import urllib.request, json
packages = [
    ("questionary", "2.1.1"),
    ("prompt_toolkit", "3.0.53"),
    ("wcwidth", "0.2.13"),
]
for pkg, ver in packages:
    data = json.loads(urllib.request.urlopen(
        f"https://pypi.org/pypi/{pkg}/{ver}/json"
    ).read())
    for f in data["urls"]:
        fname = f["filename"]
        if fname.endswith("-py3-none-any.whl") or fname.endswith("-py2.py3-none-any.whl"):
            print(pkg, fname, f["url"])
EOF
```

> If the PyPI version for wcwidth doesn't match what's in vendor/ (0.8.2 vs 0.2.x), use the version that IS on PyPI and verify the sha256 matches the vendored wheel by downloading: `curl -L <pypi-url> -o /tmp/whl && shasum -a 256 /tmp/whl`. If sha256 doesn't match, document the discrepancy and use the sha256 of the vendored file — it was the one actually tested.

The devflow-sdk URL follows the GitHub Releases pattern (no PyPI lookup needed):
```
https://github.com/captainwonderwall/devflow-platform/releases/download/devflow-sdk%2Fv0.3.2/devflow_sdk-0.3.2-py3-none-any.whl
```

- [ ] **Step 3: Write the updated formula**

Replace `homebrew-devflow/Formula/devflow.rb` entirely with (substituting the actual sha256 and PyPI URLs from steps 1-2):

```ruby
class Devflow < Formula
  desc "AI-powered developer workflow scripts"
  homepage "https://github.com/captainwonderwall/devflow-platform"
  url "https://github.com/captainwonderwall/devflow-platform.git",
      tag:      "devflow/v0.4.4",
      revision: "62cd739bf5f024323792c7e86253cc27952a9553"
  license "MIT"
  head "https://github.com/captainwonderwall/devflow-platform.git", branch: "main"

  depends_on "python@3"

  resource "devflow-sdk" do
    url "https://github.com/captainwonderwall/devflow-platform/releases/download/devflow-sdk%2Fv0.3.2/devflow_sdk-0.3.2-py3-none-any.whl"
    sha256 "<sha256-from-step-1>"
  end

  resource "questionary" do
    url "<pypi-url-from-step-2>"
    sha256 "<sha256-from-step-1>"
  end

  resource "prompt_toolkit" do
    url "<pypi-url-from-step-2>"
    sha256 "<sha256-from-step-1>"
  end

  resource "wcwidth" do
    url "<pypi-url-from-step-2>"
    sha256 "<sha256-from-step-1>"
  end

  def install
    libexec.install Dir["devflow/*"]

    python_packages = libexec/"python-packages"
    python_packages.mkpath
    resources.each do |r|
      r.stage do
        system "pip3", "install", "--no-deps", "--target=#{python_packages}", Pathname.pwd
      end
    end

    %w[draft-pr address-pr squash-commits finish-issue start-issue].each do |tool|
      (bin/tool).write <<~BASH
        #!/bin/bash
        export PYTHONPATH="#{libexec}/plugin-manager:#{python_packages}${PYTHONPATH:+:$PYTHONPATH}"
        exec python3 "#{libexec}/#{tool}/#{tool}.py" "$@"
      BASH
      (bin/tool).chmod 0755
    end

    (bin/"devflow-plugin").write <<~BASH
      #!/bin/bash
      export PYTHONPATH="#{libexec}/plugin-manager:#{python_packages}${PYTHONPATH:+:$PYTHONPATH}"
      exec python3 "#{libexec}/plugin-manager/plugin_loader.py" "$@"
    BASH
    (bin/"devflow-plugin").chmod 0755
  end

  def caveats
    <<~EOS
      To finish setup, run the shell integration script once:
        bash #{opt_libexec}/scripts/setup-shell.sh
      Then reload your shell:
        source ~/.zshrc
    EOS
  end

  test do
    system "python3", "-c",
      "import sys; sys.path.insert(0, '#{libexec}/python-packages'); import questionary"
  end
end
```

- [ ] **Step 4: Verify Ruby syntax**

```bash
ruby -c homebrew-devflow/Formula/devflow.rb
```
Expected: `Syntax OK`

- [ ] **Step 5: Commit**

```bash
git add homebrew-devflow/Formula/devflow.rb
git commit -m "chore: replace vendor wheel install with homebrew resource blocks in devflow formula"
```

---

## Task 2: Remove devflow/vendor/ and simplify CI devflow-tests

**Files:**
- Delete: `devflow/vendor/` (all 4 .whl files + directory)
- Delete: `devflow/conftest.py`
- Delete: `devflow/scripts/update-vendor.sh`
- Modify: `.github/workflows/ci.yml` (devflow-tests job)

**Interfaces:**
- Consumes: Task 1 committed formula (sha256s recorded; vendor wheels no longer needed)
- Produces: devflow tests run via uv directly from devflow-sdk source, no wheel copy step

- [ ] **Step 1: Delete vendor files and conftest**

```bash
rm -rf devflow/vendor/
rm devflow/conftest.py
rm devflow/scripts/update-vendor.sh
```

- [ ] **Step 2: Verify devflow tests still pass with uv**

```bash
uv venv
uv pip install -e "devflow-sdk/[dev]"
uv run --no-project pytest devflow/
```
Expected: all tests pass. `devflow-sdk` and `questionary` are installed into the uv venv by the editable install (questionary is a dependency of devflow-sdk).

- [ ] **Step 3: Update `.github/workflows/ci.yml` — devflow-tests job**

Replace the `devflow-tests` job with:

```yaml
  devflow-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv venv
      - run: uv pip install -e "devflow-sdk/[dev]"
      - run: uv run --no-project pytest devflow/
```

The removed steps are the `uv build`, `rm -f devflow/vendor/`, and `cp` lines that rebuilt and copied the wheel.

- [ ] **Step 4: Commit**

```bash
git add -u devflow/vendor devflow/conftest.py devflow/scripts/update-vendor.sh .github/workflows/ci.yml
git commit -m "chore: remove devflow vendor wheels — deps now resolved via uv and homebrew resources"
```

---

## Task 3: Add platform justfiles

**Files:**
- Create: `justfile`
- Create: `devflow-sdk/justfile`

**Interfaces:**
- Produces: `just test`, `just test-sdk`, `just test-devflow`, `just test-scaffold` in repo root; `just test`, `just dev`, `just build` in devflow-sdk/

- [ ] **Step 1: Create root `justfile`**

```just
# List available recipes
default:
    just --list

# Run all test suites
test: test-sdk test-devflow test-scaffold

# Run devflow-sdk unit tests
test-sdk:
    cd devflow-sdk && uv run --extra dev pytest

# Run devflow tool tests
test-devflow:
    #!/bin/bash
    set -euo pipefail
    uv venv
    uv pip install -e "devflow-sdk/[dev]"
    uv run --no-project pytest devflow/

# Run scaffold tests (integration test enabled via DEVFLOW_SDK)
test-scaffold:
    DEVFLOW_SDK="$(pwd)/devflow-sdk" bash devflow-plugin-scaffold/tests/test_scaffold.sh
```

- [ ] **Step 2: Create `devflow-sdk/justfile`**

```just
# List available recipes
default:
    just --list

# Install dev dependencies into a local venv
dev:
    uv sync --extra dev

# Run tests
test:
    uv run --extra dev pytest

# Build wheel
build:
    uv build --wheel
```

- [ ] **Step 3: Verify justfiles work**

```bash
just --list
just test-sdk
```
Expected: `just --list` prints all recipes; `just test-sdk` runs pytest in devflow-sdk and passes.

- [ ] **Step 4: Commit**

```bash
git add justfile devflow-sdk/justfile
git commit -m "chore: add justfiles for standard dev commands across monorepo"
```

---

## Task 4: Update release.sh and enable scaffold CI integration test

**Files:**
- Modify: `scripts/release.sh` (lines 137–149)
- Modify: `.github/workflows/ci.yml` (scaffold-tests job)

**Interfaces:**
- Produces: when SDK releases, `release.sh` downloads the new wheel to compute sha256 and updates the formula resource block instead of committing a vendor wheel. Scaffold CI integration test runs with DEVFLOW_SDK pointing to the local SDK source.

- [ ] **Step 1: Update `scripts/release.sh` — replace lines 137–149**

Find and replace this exact block in `scripts/release.sh`:

```bash
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
```

With:

```bash
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
```

- [ ] **Step 2: Update `.github/workflows/ci.yml` — scaffold-tests job**

Replace the `scaffold-tests` job with:

```yaml
  scaffold-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: DEVFLOW_SDK="${{ github.workspace }}/devflow-sdk" bash devflow-plugin-scaffold/tests/test_scaffold.sh
```

- [ ] **Step 3: Verify scaffold tests run with DEVFLOW_SDK locally**

```bash
DEVFLOW_SDK="$(pwd)/devflow-sdk" bash devflow-plugin-scaffold/tests/test_scaffold.sh
```
Expected: all existing assertions pass; integration test now runs (not skipped).

- [ ] **Step 4: Commit**

```bash
git add scripts/release.sh .github/workflows/ci.yml
git commit -m "chore: update release.sh to patch formula resource block on sdk release; enable scaffold CI integration test"
```

---

## Task 5: Add failing test_scaffold.sh assertions (TDD)

**Files:**
- Modify: `devflow-plugin-scaffold/tests/test_scaffold.sh`

**Interfaces:**
- Produces: 15 new assertions that all FAIL before scaffold.sh is updated. Tasks 6–8 make them pass.

- [ ] **Step 1: Add assertions after the existing `acme-format` block**

In `test_scaffold.sh`, after the last existing `has_content`/`no_content` assertion for the `acme-format` block (around line 62, before the single-word name section), add:

```bash
# ── new assertions: justfile ───────────────────────────────────────────────────
file_exists  "$D/justfile"
has_content  "$D/justfile"                                     "test:"
has_content  "$D/justfile"                                     "vendor:"
has_content  "$D/justfile"                                     "uv run --extra dev pytest"

# ── new assertions: ci.yml ────────────────────────────────────────────────────
file_exists  "$D/.github/workflows/ci.yml"
has_content  "$D/.github/workflows/ci.yml"                     "uv run --extra dev pytest"
has_content  "$D/.github/workflows/ci.yml"                     "astral-sh/setup-uv"

# ── new assertions: release.yml test gate ────────────────────────────────────
has_content  "$D/.github/workflows/release.yml"                "needs: test"
no_content   "$D/.github/workflows/release.yml"                "acme_format.py"

# ── new assertions: conftest.py ───────────────────────────────────────────────
file_exists  "$D/conftest.py"
has_content  "$D/conftest.py"                                  "sys.path.insert"

# ── new assertions: vendor/ ───────────────────────────────────────────────────
file_exists  "$D/vendor/.gitkeep"

# ── new assertions: update-vendor.sh ─────────────────────────────────────────
file_exists  "$D/scripts/update-vendor.sh"
has_content  "$D/scripts/update-vendor.sh"                     "uv pip download"

# ── new assertions: pyproject.toml git URL ───────────────────────────────────
has_content  "$D/pyproject.toml"   "git+https://github.com/captainwonderwall/devflow-platform"
no_content   "$D/pyproject.toml"   "devflow-sdk>="

# ── new assertions: .gitignore ────────────────────────────────────────────────
has_content  "$D/.gitignore"                                   ".venv/"

# ── new assertions: formula uses tarball URL and installs vendor/ ─────────────
has_content  "$D/Formula/devflow-plugin-acme-format.rb"        "archive/refs/tags"
has_content  "$D/Formula/devflow-plugin-acme-format.rb"        "vendor"
```

- [ ] **Step 2: Run test_scaffold.sh to confirm new assertions fail**

```bash
DEVFLOW_SDK="$(pwd)/devflow-sdk" bash devflow-plugin-scaffold/tests/test_scaffold.sh
```
Expected: the summary shows several FAIL lines corresponding to the new assertions. Existing assertions still pass.

- [ ] **Step 3: Commit the failing tests**

```bash
git add devflow-plugin-scaffold/tests/test_scaffold.sh
git commit -m "test: add failing scaffold assertions for new generated files and dependency model"
```

---

## Task 6: Update scaffold — fix existing generated content

**Files:**
- Modify: `devflow-plugin-scaffold/scaffold.sh` (pyproject.toml heredoc, plugin .py heredoc, .gitignore heredoc, README heredoc)

**Interfaces:**
- Consumes: failing assertions from Task 5 for pyproject.toml, .gitignore, release.yml
- Produces: those assertions pass

- [ ] **Step 1: Update the pyproject.toml heredoc in scaffold.sh**

Find (around line 106):
```bash
cat > "$PLUGIN_NAME/pyproject.toml" << EOF
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "${PLUGIN_NAME}"
version = "0.1.0"
requires-python = ">=3.11"

[project.optional-dependencies]
dev = [
    "devflow-sdk>=0.1.0,<1.0",
    "pytest>=7.0",
]
EOF
```

Replace with:
```bash
cat > "$PLUGIN_NAME/pyproject.toml" << 'EOF'
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "PLUGIN_NAME_PLACEHOLDER"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    # Plugin-specific runtime extras (PyPI packages).
    # devflow-sdk is NOT here — devflow provides it at runtime.
]

[project.optional-dependencies]
dev = [
    "devflow-sdk @ git+https://github.com/captainwonderwall/devflow-platform@devflow-sdk/v0.3.2#subdirectory=devflow-sdk",
    "pytest>=8",
    "build>=1.0",
]
EOF
sed -i.bak "s/PLUGIN_NAME_PLACEHOLDER/${PLUGIN_NAME}/g" "$PLUGIN_NAME/pyproject.toml" \
    && rm "$PLUGIN_NAME/pyproject.toml.bak"
```

> Note: the heredoc uses `'EOF'` (single-quoted) to prevent variable expansion inside it, then a separate `sed` handles the plugin name substitution.

- [ ] **Step 2: Update the plugin .py heredoc to add sys.path injection**

Find (around line 35):
```bash
cat > "$PLUGIN_NAME/${MODULE_NAME}.py" << 'PYEOF'
from devflow_sdk.draft_pr_plugin import DraftPrPlugin
```

Replace those two lines with:
```bash
cat > "$PLUGIN_NAME/${MODULE_NAME}.py" << 'PYEOF'
import glob as _glob, os as _os, sys as _sys
_vendor = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "vendor")
for _whl in _glob.glob(_os.path.join(_vendor, "*.whl")):
    if _whl not in _sys.path:
        _sys.path.insert(0, _whl)
del _glob, _os, _sys, _vendor

from devflow_sdk.draft_pr_plugin import DraftPrPlugin
```

- [ ] **Step 3: Update the .gitignore heredoc to add .venv/**

Find (around line 402):
```bash
cat > "$PLUGIN_NAME/.gitignore" << 'EOF'
__pycache__/
*.pyc
*.pyo
.pytest_cache/
*.egg-info/
dist/
build/
EOF
```

Replace with:
```bash
cat > "$PLUGIN_NAME/.gitignore" << 'EOF'
__pycache__/
*.pyc
*.pyo
.pytest_cache/
*.egg-info/
dist/
build/
.venv/
EOF
```

- [ ] **Step 4: Update the README Develop section heredoc**

Find (around line 228):
```bash
## Develop

\`\`\`bash
# Install dev dependencies (or point PYTHONPATH at a local devflow-sdk clone)
pip install devflow-sdk pytest

# Run tests — no AI required
PYTHONPATH=. pytest tests/
\`\`\`
```

Replace with:
```bash
## Prerequisites

Install once per machine:

\`\`\`bash
brew install uv just
\`\`\`

## Develop

Install dev dependencies (one-time per repo):

\`\`\`bash
just dev
\`\`\`

Run tests:

\`\`\`bash
just test
\`\`\`

If your plugin has runtime extras beyond devflow-sdk, add them to
\`[project.dependencies]\` in \`pyproject.toml\` and run:

\`\`\`bash
just vendor
\`\`\`

This downloads the wheels into \`vendor/\` — commit the result.
```

- [ ] **Step 5: Run scaffold tests**

```bash
DEVFLOW_SDK="$(pwd)/devflow-sdk" bash devflow-plugin-scaffold/tests/test_scaffold.sh
```
Expected: the `pyproject.toml` git URL, `no_content "devflow-sdk>="`, and `.gitignore .venv/` assertions now pass. Formula and justfile assertions still fail (those are Tasks 7–8).

- [ ] **Step 6: Commit**

```bash
git add devflow-plugin-scaffold/scaffold.sh
git commit -m "fix: update scaffold generated content — git URL for sdk dep, sys.path injection, .venv gitignore, updated README"
```

---

## Task 7: Update scaffold — add new generated files

**Files:**
- Modify: `devflow-plugin-scaffold/scaffold.sh` (add 5 new heredoc blocks)

**Interfaces:**
- Consumes: failing assertions for justfile, ci.yml, conftest.py, vendor/.gitkeep, update-vendor.sh
- Produces: those assertions pass

- [ ] **Step 1: Add justfile generation block**

After the `.gitignore` block (around line 412), add:

```bash
# ── justfile ──────────────────────────────────────────────────────────────────
cat > "$PLUGIN_NAME/justfile" << 'EOF'
# List available recipes
default:
    just --list

# Install dev dependencies into a local venv
dev:
    uv sync --extra dev

# Run tests
test:
    uv run --extra dev pytest tests/

# Build wheel
build:
    uv build --wheel

# Refresh vendor/ from declared runtime deps in pyproject.toml
vendor:
    bash scripts/update-vendor.sh
EOF
```

- [ ] **Step 2: Add CI workflow generation block**

The scaffold already has a `release.yml` block; add a separate `ci.yml` block. After the justfile block, add:

```bash
# ── GitHub Actions CI workflow ────────────────────────────────────────────────
mkdir -p "$PLUGIN_NAME/.github/workflows"
cat > "$PLUGIN_NAME/.github/workflows/ci.yml" << 'YAMEOF'
name: CI
on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv run --extra dev pytest tests/
YAMEOF
```

- [ ] **Step 3: Add conftest.py generation block**

After the CI workflow block, add:

```bash
# ── conftest.py ───────────────────────────────────────────────────────────────
cat > "$PLUGIN_NAME/conftest.py" << 'PYEOF'
import glob, os, sys
_vendor = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")
for _whl in sorted(glob.glob(os.path.join(_vendor, "*.whl"))):
    if _whl not in sys.path:
        sys.path.insert(0, _whl)
PYEOF
```

- [ ] **Step 4: Add vendor/.gitkeep creation**

After the conftest.py block, add:

```bash
# ── vendor/ directory ─────────────────────────────────────────────────────────
mkdir -p "$PLUGIN_NAME/vendor"
touch "$PLUGIN_NAME/vendor/.gitkeep"
```

- [ ] **Step 5: Add scripts/update-vendor.sh generation block**

After the vendor block, add:

```bash
# ── scripts/update-vendor.sh ─────────────────────────────────────────────────
mkdir -p "$PLUGIN_NAME/scripts"
cat > "$PLUGIN_NAME/scripts/update-vendor.sh" << 'SHEOF'
#!/bin/bash
# Downloads wheel files for this plugin's runtime deps into vendor/.
# Run after changing [project.dependencies] in pyproject.toml.
# Commit the resulting vendor/ changes.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$REPO_ROOT/vendor"
mkdir -p "$VENDOR"

deps=$(python3 -c "
import tomllib
with open('$REPO_ROOT/pyproject.toml', 'rb') as f:
    data = tomllib.load(f)
deps = data.get('project', {}).get('dependencies', [])
if deps:
    print(' '.join(deps))
")

if [[ -z \"\$deps\" ]]; then
    echo \"No runtime dependencies declared — vendor/ stays empty.\"
    exit 0
fi

rm -f \"\$VENDOR\"/*.whl
uv pip download --no-deps --output-dir \"\$VENDOR\" \$deps
echo \"vendor/ updated.\"
SHEOF
chmod +x "$PLUGIN_NAME/scripts/update-vendor.sh"
```

> Note: the `$` signs inside the heredoc for variables that should expand at PLUGIN runtime (not scaffold time) are escaped with `\"` — the heredoc uses `'SHEOF'` quoting but the variable references inside refer to the generated script's own variables. Double-check escaping carefully: `$REPO_ROOT`, `$VENDOR`, `$deps` in the generated script must not be expanded by scaffold.sh itself.

Actually, to avoid escaping confusion: use a single-quoted heredoc marker (`'SHEOF'`) so nothing inside is expanded by scaffold.sh. All `$` signs are literal in the output.

- [ ] **Step 6: Run scaffold tests**

```bash
DEVFLOW_SDK="$(pwd)/devflow-sdk" bash devflow-plugin-scaffold/tests/test_scaffold.sh
```
Expected: justfile, ci.yml, conftest.py, vendor/.gitkeep, update-vendor.sh assertions now pass. Formula and release.yml test-gate assertions still fail.

- [ ] **Step 7: Commit**

```bash
git add devflow-plugin-scaffold/scaffold.sh
git commit -m "feat: scaffold now generates justfile, ci.yml, conftest.py, vendor/, and update-vendor.sh"
```

---

## Task 8: Update scaffold — fix Homebrew formula template and release.yml

**Files:**
- Modify: `devflow-plugin-scaffold/scaffold.sh` (formula heredoc, release.yml heredoc)

**Interfaces:**
- Consumes: failing assertions for formula tarball URL + vendor install, release.yml test gate
- Produces: all 15 Task 5 assertions pass

- [ ] **Step 1: Update the formula heredoc**

Find the formula heredoc block (around line 144). Replace the entire `cat > "$PLUGIN_NAME/Formula/..."` block with:

```bash
# ── Homebrew formula template ────────────────────────────────────────────────
cat > "$PLUGIN_NAME/Formula/devflow-plugin-${PLUGIN_NAME}.rb" << 'RBEOF'
class __FORMULA_CLASS_NAME__ < Formula
  desc "devflow plugin: __DISPLAY_NAME__"
  homepage "<your-plugin-homepage>"
  url "https://github.com/<your-org>/__PLUGIN_NAME__/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "<sha256-of-tarball>"
  version "0.1.0"

  depends_on "captainwonderwall/devflow/devflow"

  def install
    lib.install "__MODULE_NAME__.py"
    vendor = lib/"vendor"
    vendor.mkpath
    Dir["vendor/*.whl"].each { |whl| vendor.install whl }
  end

  def post_install
    system "#{HOMEBREW_PREFIX}/bin/devflow-plugin",
           "register", "__PLUGIN_NAME__",
           "#{opt_lib}/__MODULE_NAME__.py",
           "--formula", "<your-tap>/__PLUGIN_NAME__"
  end

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
    "$PLUGIN_NAME/Formula/devflow-plugin-${PLUGIN_NAME}.rb" \
    && rm "$PLUGIN_NAME/Formula/devflow-plugin-${PLUGIN_NAME}.rb.bak"
```

- [ ] **Step 2: Update the release.yml heredoc**

Find the release.yml heredoc (around line 179). Replace the entire block with:

```bash
# ── GitHub Actions release workflow ───────────────────────────────────────────
cat > "$PLUGIN_NAME/.github/workflows/release.yml" << 'YAMEOF'
name: Release

on:
  push:
    tags:
      - "v*"

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv run --extra dev pytest tests/

  release:
    needs: test
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
            --generate-notes
YAMEOF
```

> The `.py` asset attachment is intentionally removed. The Homebrew formula now downloads the repo tarball (auto-generated by GitHub for every tag), so no release asset needs to be attached.

- [ ] **Step 3: Update `has_content` assertion for release.yml in test_scaffold.sh**

The existing assertion checks for `'GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}'` — this is still present, so it passes. But also verify there is an existing assertion that checks `acme_format.py` is referenced in the release.yml. If so, that assertion must be changed to `no_content`:

Find in `test_scaffold.sh`:
```bash
has_content "$D/.github/workflows/release.yml"    "acme_format.py"
```
Change to:
```bash
no_content  "$D/.github/workflows/release.yml"    "acme_format.py"
```

- [ ] **Step 4: Run scaffold tests — all 15 new assertions must pass**

```bash
DEVFLOW_SDK="$(pwd)/devflow-sdk" bash devflow-plugin-scaffold/tests/test_scaffold.sh
```
Expected: `Results: N passed, 0 failed`

- [ ] **Step 5: Commit**

```bash
git add devflow-plugin-scaffold/scaffold.sh devflow-plugin-scaffold/tests/test_scaffold.sh
git commit -m "fix: scaffold formula uses tarball URL with vendor install; release.yml gates on tests"
```

---

## Task 9: Final verification

**Files:** none — read-only verification only

- [ ] **Step 1: Run full monorepo test suite via just**

```bash
just test
```
Expected: all three suites pass — sdk-tests, devflow-tests, scaffold-tests (with integration test now running, not skipped).

- [ ] **Step 2: Verify scaffold integration test ran (not skipped)**

```bash
DEVFLOW_SDK="$(pwd)/devflow-sdk" bash devflow-plugin-scaffold/tests/test_scaffold.sh 2>&1 | grep -i skip
```
Expected: no "SKIP" lines in output.

- [ ] **Step 3: Verify a scaffolded plugin's tests pass end-to-end**

```bash
cd /tmp
bash "$(pwd -P)/../devflow-plugin-scaffold/scaffold.sh" smoke-test-plugin
cd smoke-test-plugin
DEVFLOW_SDK="path/to/devflow-sdk" PYTHONPATH=. python3 -m pytest tests/ -v
cd ..
rm -rf smoke-test-plugin
```

Actually, use the justfile if just is installed:
```bash
tmpdir=$(mktemp -d)
(cd "$tmpdir" && bash "$OLDPWD/devflow-plugin-scaffold/scaffold.sh" smoke)
(cd "$tmpdir/smoke" && DEVFLOW_SDK="$OLDPWD/devflow-sdk" uv run --extra dev pytest tests/)
rm -rf "$tmpdir"
```
Expected: 4 tests pass.

- [ ] **Step 4: Verify formula Ruby syntax**

```bash
ruby -c homebrew-devflow/Formula/devflow.rb
```
Expected: `Syntax OK`

- [ ] **Step 5: Commit the spec and plan (if not already committed)**

```bash
git add docs/superpowers/specs/2026-08-25-consistent-dependency-management-design.md \
        docs/superpowers/plans/2026-08-25-consistent-dependency-management.md
git commit -m "docs: add design spec and implementation plan for consistent dependency management"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| devflow-sdk git URL dep in pyproject.toml | Task 6 |
| uv as standard tool everywhere | Tasks 3, 6, 7 |
| justfile with dev/test/build/vendor recipes | Tasks 3, 7 |
| Remove devflow/vendor/ committed wheels | Task 2 |
| Remove devflow/conftest.py | Task 2 |
| Remove devflow/scripts/update-vendor.sh | Task 2 |
| Homebrew formula resource blocks | Task 1 |
| CI devflow-tests simplified | Task 2 |
| CI scaffold-tests DEVFLOW_SDK set | Task 4 |
| release.sh replace vendor commit with formula update | Task 4 |
| Scaffold: pyproject.toml git URL | Task 6 |
| Scaffold: plugin .py sys.path injection | Task 6 |
| Scaffold: .gitignore + .venv/ | Task 6 |
| Scaffold: README (just dev/test/vendor) | Task 6 |
| Scaffold: generate justfile | Task 7 |
| Scaffold: generate ci.yml | Task 7 |
| Scaffold: generate conftest.py | Task 7 |
| Scaffold: generate vendor/.gitkeep | Task 7 |
| Scaffold: generate scripts/update-vendor.sh | Task 7 |
| Scaffold: formula tarball URL + vendor install | Task 8 |
| Scaffold: release.yml test gate | Task 8 |
| test_scaffold.sh assertions | Task 5 + Task 8 Step 3 |

All spec requirements are covered. No gaps found.

**Placeholder scan:** No TBDs. sha256 values in Task 1 are computed by the implementer as part of the task steps — this is real work, not a placeholder.

**Type consistency:** No shared function signatures across tasks. Each task is self-contained bash/Python/Ruby — no type mismatches possible.
