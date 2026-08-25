# Consistent Dependency Management and Developer Workflow

**Date:** 2026-08-25
**Issue:** [#15](https://github.com/captainwonderwall/devflow-platform/issues/15)

---

## Context

The devflow platform is a Python monorepo with three subprojects:

- **`devflow-sdk/`** — shared library; the contract between devflow and plugins
- **`devflow/`** — the installed CLI tools (draft-pr, address-pr, etc.)
- **`devflow-plugin-scaffold/`** — a scaffold generator that plugin authors use to bootstrap standalone plugin repos

Plugins are distributed as standalone repos, loaded **in-process** by devflow's `plugin_loader.py` via `importlib.util.spec_from_file_location`. When a devflow tool runs, it sets `PYTHONPATH` to include `#{libexec}/plugin-manager` and `#{libexec}/python-packages`. Any plugin loaded in that process inherits the same `sys.path` — so `devflow_sdk` and its own deps (questionary, etc.) are always available to plugins for free.

**Current gaps:**

1. `devflow-sdk` is not on PyPI; no scriptable way to install it in dev or CI
2. `devflow/vendor/` commits binary wheel files that must be manually kept in sync
3. Plugins have no CI workflow that runs their tests
4. No standard commands for build/test across the platform or plugin repos
5. The scaffold generates broken dev instructions (`pip install devflow-sdk pytest` fails)
6. The scaffold integration test is always skipped in CI because `DEVFLOW_SDK` is never set

---

## Goals

- `just test` works identically in any context: the monorepo, devflow-sdk, or a plugin repo
- `just dev` sets up a dev environment in one command, no global pip installs
- No binary wheel files committed to any repo — deps are declared and resolved at dev/CI/install time
- Plugin authors declare dependencies (`devflow-sdk` + their own extras) and those deps are honored in dev, CI, and at Homebrew runtime
- uv is the single tool for all Python operations; no manual venv activation required
- The scaffold generates everything a plugin author needs out of the box

## Non-goals

- Publishing `devflow-sdk` to PyPI
- Changing how devflow loads plugins (`plugin_loader.py` is unchanged)

---

## Developer Tooling Prerequisites

Two tools are required once per machine. Neither is needed by end users who install devflow via Homebrew.

```bash
brew install uv    # Python package manager (fast pip/venv replacement)
brew install just  # Command runner (cross-platform make alternative)
```

`just` is chosen over `make` because it has cleaner syntax (no tab requirements, no `.PHONY` declarations), built-in `just --list` documentation, and works on Windows as well as macOS/Linux. `uv` is already used in CI.

---

## Dependency Model

### devflow-sdk is a "provided" runtime dependency

At runtime, `devflow_sdk` is always available because devflow's Homebrew formula installs it and sets `PYTHONPATH` before invoking any tool. Plugins get `devflow_sdk` for free — they must not vendor or install it themselves.

For development and CI, `devflow-sdk` is installed from its git tag using a standard pip/uv-compatible URL:

```
devflow-sdk @ git+https://github.com/captainwonderwall/devflow-platform@devflow-sdk/v0.3.2#subdirectory=devflow-sdk
```

This requires no PyPI entry and no manual wheel download. `uv` resolves it automatically. The version pin must be updated whenever a new SDK release ships.

### pyproject.toml structure — plugins

```toml
[project]
name = "acme-format"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    # Plugin-specific runtime extras only (PyPI packages).
    # devflow-sdk is NOT here — devflow provides it at runtime.
    # Example: "requests>=2.28"
]

[project.optional-dependencies]
dev = [
    # devflow-sdk declared here only for dev/CI — provided by devflow at runtime.
    "devflow-sdk @ git+https://github.com/captainwonderwall/devflow-platform@devflow-sdk/v0.3.2#subdirectory=devflow-sdk",
    "pytest>=8",
    "build>=1.0",
]
```

`[project.dependencies]` declares only what the plugin itself needs beyond devflow's baseline. `devflow-sdk` lives in `dev` extras so `uv run --extra dev pytest` installs it automatically without polluting the runtime declaration.

### pyproject.toml structure — devflow-sdk

No changes. devflow-sdk's own `pyproject.toml` already declares only `pytest>=8` and `build>=1.0` as dev deps.

### Runtime delivery for plugin extras

Plugin extras (`[project.dependencies]`) are committed as wheels in `vendor/` and injected into `sys.path` at runtime. This is the same pattern as devflow's current runtime delivery, applied at the plugin level.

**`scripts/update-vendor.sh`** reads `[project.dependencies]` from `pyproject.toml` and refreshes `vendor/`:

```bash
#!/bin/bash
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

if [[ -z "$deps" ]]; then
    echo "No runtime dependencies declared — vendor/ stays empty."
    exit 0
fi

rm -f "$VENDOR"/*.whl
uv pip download --no-deps --output-dir "$VENDOR" $deps
echo "vendor/ updated."
```

**Plugin `.py` file** — sys.path injection at the top, before any third-party imports:

```python
import glob as _glob, os as _os, sys as _sys
_vendor = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "vendor")
for _whl in _glob.glob(_os.path.join(_vendor, "*.whl")):
    if _whl not in _sys.path:
        _sys.path.insert(0, _whl)
del _glob, _os, _sys, _vendor
```

**`conftest.py`** (same injection, for the test environment):

```python
import glob, os, sys
_vendor = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")
for _whl in sorted(glob.glob(os.path.join(_vendor, "*.whl"))):
    if _whl not in sys.path:
        sys.path.insert(0, _whl)
```

`devflow-sdk` is NOT in `vendor/`. At test time it is installed by `uv run --extra dev`, which resolves the git URL dep.

---

## uv as the Standard Python Tool

`uv` manages all Python operations. No manual venv creation, no `source .venv/bin/activate`, no global `pip install`.

`uv run --extra dev <cmd>` automatically creates an isolated venv, installs declared deps (including the git URL for `devflow-sdk`), and runs the command. The venv is local to the project directory and never pollutes the system.

---

## Standard `justfile`

Every project — platform subprojects and generated plugin repos — gets a `justfile` with identical recipe names.

### Plugin `justfile`

```just
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
```

### Platform monorepo root `justfile`

With vendor/ removed from devflow/ (see below), `test-devflow` no longer needs to rebuild and copy the wheel — uv installs devflow-sdk directly from the local source.

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

### `devflow-sdk/justfile`

```just
default:
    just --list

dev:
    uv sync --extra dev

test:
    uv run --extra dev pytest

build:
    uv build --wheel
```

No `vendor` recipe — the SDK has no runtime extras.

---

## Changes to the Platform

### Removing `devflow/vendor/` — replacing with Homebrew resource blocks

Currently `devflow/vendor/` commits four wheel files that the Homebrew formula installs at `pip install --target` time. These binary files must be manually kept in sync, and the `devflow-tests` CI job rebuilds and re-copies the SDK wheel on every run.

Instead, the formula declares each dependency as a `resource` block — the Homebrew-native pattern for Python deps. Resources are fetched and verified by sha256 at `brew install` time, so there are no committed binaries in the repo.

**Updated `homebrew-devflow/Formula/devflow.rb`:**

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

  # devflow-sdk wheel from GitHub Releases (not on PyPI)
  resource "devflow-sdk" do
    url "https://github.com/captainwonderwall/devflow-platform/releases/download/devflow-sdk%2Fv0.3.2/devflow_sdk-0.3.2-py3-none-any.whl"
    sha256 "<sha256-of-devflow_sdk-0.3.2-py3-none-any.whl>"
  end

  resource "questionary" do
    url "https://files.pythonhosted.org/packages/py3/q/questionary/questionary-2.1.1-py3-none-any.whl"
    sha256 "<sha256>"
  end

  resource "prompt_toolkit" do
    url "https://files.pythonhosted.org/packages/py3/p/prompt_toolkit/prompt_toolkit-3.0.53-py3-none-any.whl"
    sha256 "<sha256>"
  end

  resource "wcwidth" do
    url "https://files.pythonhosted.org/packages/py3/w/wcwidth/wcwidth-0.2.13-py3-none-any.whl"
    sha256 "<sha256>"
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

The sha256 values for each resource are filled in during implementation by running `shasum -a 256` on the downloaded wheel files.

**Files removed from the repo:**

- `devflow/vendor/devflow_sdk-*.whl`
- `devflow/vendor/questionary-*.whl`
- `devflow/vendor/prompt_toolkit-*.whl`
- `devflow/vendor/wcwidth-*.whl`
- `devflow/vendor/` directory (entirely)
- `devflow/scripts/update-vendor.sh` (only existed to keep vendor/ in sync)

**`devflow/conftest.py` — removed**

The current conftest.py injects vendor/ wheels into sys.path for tests. With vendor/ gone, devflow-sdk and questionary are installed into the uv venv by `uv pip install -e "devflow-sdk/[dev]"` (devflow-sdk declares questionary as a dep). The conftest.py is no longer needed.

### `.github/workflows/ci.yml`

Two changes:

**`devflow-tests` job** — simplified. The wheel rebuild and copy step is removed; uv installs devflow-sdk (and its transitive dep questionary) directly.

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

**`scaffold-tests` job** — `DEVFLOW_SDK` added so the integration test runs instead of being silently skipped:

```yaml
scaffold-tests:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: astral-sh/setup-uv@v4
    - run: DEVFLOW_SDK="${{ github.workspace }}/devflow-sdk" bash devflow-plugin-scaffold/tests/test_scaffold.sh
```

### `scripts/release.sh`

The SDK release section (lines 137–149) currently calls `devflow/scripts/update-vendor.sh` to download the new wheel into `devflow/vendor/` and commits it. This is replaced by updating the formula's `resource` block instead.

**Removed:**
```bash
echo "==> Updating devflow vendor wheel..."
bash devflow/scripts/update-vendor.sh "v${SDK_NEXT}"
git add devflow/vendor/
if ! git diff --cached --quiet -- devflow/vendor/; then
  git commit -m "chore: update devflow-sdk vendor wheel to v${SDK_NEXT}"
  if ! $DEVFLOW_RELEASE; then
    DEVFLOW_RELEASE=true
    DEVFLOW_NEXT=$(apply_bump "${DEVFLOW_CURRENT:-0.0.0}" "$(semver_bump_for "$DEVFLOW_LAST" "devflow/")")
  fi
fi
```

**Replaced with:**
```bash
echo "==> Updating devflow-sdk resource block in Homebrew formula..."
WHEEL_FILENAME="devflow_sdk-${SDK_NEXT/v/}-py3-none-any.whl"
WHEEL_URL="https://github.com/captainwonderwall/devflow-platform/releases/download/devflow-sdk%2Fv${SDK_NEXT/v/}/${WHEEL_FILENAME}"
gh release download "devflow-sdk/v${SDK_NEXT/v/}" \
  --repo captainwonderwall/devflow-platform \
  --pattern "devflow_sdk-*.whl" \
  --dir "$TMPDIR" --clobber
WHEEL_SHA256=$(shasum -a 256 "$TMPDIR/${WHEEL_FILENAME}" | awk '{print $1}')

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
  git commit -m "chore: update devflow-sdk resource to v${SDK_NEXT/v/} in homebrew formula"
  if ! $DEVFLOW_RELEASE; then
    DEVFLOW_RELEASE=true
    DEVFLOW_NEXT=$(apply_bump "${DEVFLOW_CURRENT:-0.0.0}" "patch")
  fi
fi
```

The re-evaluate-devflow-release logic is preserved: if SDK changed, devflow still gets a new release so the formula update ships. `devflow/scripts/update-vendor.sh` is deleted.

### Root `justfile` and `devflow-sdk/justfile`

New files as shown in the Standard justfile section above.

---

## Changes to the Scaffold

`scaffold.sh` generates the following new and updated files for each plugin repo:

### New: `justfile`

Standard plugin recipes as above, including `vendor`.

### New: `.github/workflows/ci.yml`

```yaml
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
```

`uv run --extra dev` resolves the `devflow-sdk` git URL automatically. No separate download step needed.

### Updated: `Formula/devflow-plugin-<name>.rb`

The current formula template has two problems:

**Problem 1 — URL points to a single `.py` release asset.** The formula installs only the `.py` file. When the plugin `.py` runs, it does `sys.path.insert` looking for `vendor/` relative to `__file__`. When installed via Homebrew, `__file__` resolves to `#{opt_lib}/acme_format.py`, so vendor/ must exist at `#{opt_lib}/vendor/` — but nothing puts it there.

**Problem 2 — No test gate.** The release job fires without verifying tests pass.

**Fix — switch to repo archive tarball URL.** GitHub automatically generates a source tarball for every tag at `https://github.com/<org>/<repo>/archive/refs/tags/<tag>.tar.gz`. This tarball includes the full repo checkout, including the committed `vendor/` directory. The formula install step copies the `.py` file and any vendor wheels into the right locations. No release asset attachment needed.

Updated formula template:

```ruby
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
```

The sha256 placeholder is filled by the plugin author after their first tagged release, using `curl -sL <tarball-url> | shasum -a 256`. The `Dir["vendor/*.whl"]` loop is a no-op for plugins with no extras; it only activates when vendor/ contains wheels.

### Updated: `.github/workflows/release.yml`

Add a `test` job that the `release` job depends on. Remove the `.py` file attachment — the Homebrew formula now uses the auto-generated tarball, so no release asset is needed.

```yaml
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
```

### Updated: `.gitignore`

Add `.venv/` — uv creates this directory automatically during `just dev` and it must not be committed.

```
__pycache__/
*.pyc
*.pyo
.pytest_cache/
*.egg-info/
dist/
build/
.venv/
```

### New: `conftest.py`

The vendor sys.path injection shown above.

### New: `vendor/` directory

An empty directory (with a `.gitkeep`) committed to the repo. Populated by `just vendor` when the plugin has runtime extras. Stays empty for plugins with no extras.

### New: `scripts/update-vendor.sh`

The script shown in the Runtime Delivery section above.

### Updated: `pyproject.toml`

Changed from bare `devflow-sdk>=0.1.0,<1.0` (which fails to resolve) to the git URL shown in the Dependency Model section.

### Updated: Plugin `.py` file

Vendor sys.path injection block added at the top, before `from devflow_sdk import ...`.

### Updated: `README.md` — Develop section

```markdown
## Prerequisites

Install once per machine:

```bash
brew install uv just
```

## Develop

Install dev dependencies (one-time per repo):

```bash
just dev
```

Run tests:

```bash
just test
```

If your plugin has runtime extras beyond devflow-sdk, add them to
`[project.dependencies]` in `pyproject.toml` and run:

```bash
just vendor
```

This downloads the wheels into `vendor/` (commit the result).
```

### Updated: `tests/test_scaffold.sh`

New assertions:

- `justfile` exists and contains `test:` recipe
- `justfile` exists and contains `vendor:` recipe
- `.github/workflows/ci.yml` exists and contains `uv run --extra dev pytest`
- `.github/workflows/release.yml` contains `needs: test` (release gated on tests)
- `.github/workflows/release.yml` does NOT contain `__MODULE_NAME__.py` as a release asset attachment (tarball approach needs no attached asset)
- `conftest.py` exists and contains `sys.path.insert`
- `pyproject.toml` contains `git+https://github.com/captainwonderwall/devflow-platform`
- `pyproject.toml` does NOT contain bare `devflow-sdk>=` under `[project.dependencies]`
- `scripts/update-vendor.sh` exists and is executable
- `vendor/.gitkeep` exists
- `.gitignore` contains `.venv/`
- `Formula/devflow-plugin-acme-format.rb` contains `archive/refs/tags` (tarball URL)
- `Formula/devflow-plugin-acme-format.rb` contains `vendor` (install step handles vendor/)

The integration test (which runs the generated plugin's test suite) already passes once `DEVFLOW_SDK` is set in CI.

---

## Developer Workflow Summary

### One-time machine setup

```bash
brew install uv just
```

### Platform developer (working on devflow-sdk or devflow tools)

```bash
git clone ...
just test          # runs all three test suites

cd devflow-sdk
just dev           # installs deps into a local venv
just test          # runs only SDK tests
just build         # builds the SDK wheel
```

### Plugin author (working on a generated plugin)

```bash
# After scaffolding:
cd acme-format
just dev           # installs devflow-sdk (via git URL) + pytest into a local venv
just test          # runs pytest — passes immediately on the stubs

# After adding a runtime dep (e.g. requests):
# 1. Add "requests>=2.28" to [project.dependencies] in pyproject.toml
# 2. just vendor   — downloads requests wheel into vendor/
# 3. git add vendor/ pyproject.toml && git commit
# 4. just test     — verifies everything works
```

### CI (both platform and plugins)

CI calls `uv` directly — no `just` required in CI. `just` is a local developer convenience only.

---

## Self-Review

- No placeholders or TBDs remaining except sha256 values in resource blocks — those are filled in during implementation by downloading and hashing each wheel
- `devflow-sdk` git URL pin and formula resource URL/sha256 must both be bumped on SDK release — two places, both explicit
- `just` is not required in CI — only for local development; CI uses `uv` directly
- Removing `devflow/vendor/` eliminates committed binaries and the CI wheel-rebuild step; the formula resource approach is the Homebrew-standard pattern
- `scripts/release.sh` SDK section is updated: vendor commit replaced by formula resource block update (URL + sha256); `devflow/scripts/update-vendor.sh` deleted
- The `justfile` recipe names (`dev`, `test`, `build`, `vendor`) are identical across all project types — a developer learns them once
