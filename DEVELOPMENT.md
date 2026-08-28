# Development Guide

This guide is for contributors to `devflow-platform` and authors building
devflow plugins. For installing and using the tools, see the main
[`README.md`](README.md).

## Repository Layout

| Directory | Purpose |
|-----------|---------|
| [`devflow/`](devflow/) | The command-line tools and their tests |
| [`devflow-sdk/`](devflow-sdk/) | Shared plugin interface and utilities |
| [`devflow-plugin-scaffold/`](devflow-plugin-scaffold/) | Scaffolds new plugin repositories |
| [`smoke-check/`](smoke-check/) | An example `draft-pr` plugin |
| [`homebrew-devflow/`](homebrew-devflow/) | Homebrew formulae |
| [`scripts/`](scripts/) | Repository bootstrap and release scripts |
| [`docs/`](docs/) | Architecture decisions and design documents |

## Set Up a Checkout

Prerequisites:

- [Homebrew](https://brew.sh)
- [GitHub CLI](https://cli.github.com)
- [uv](https://docs.astral.sh/uv/)

```bash
git clone git@github.com:captainwonderwall/devflow-platform.git
cd devflow-platform
bash scripts/bootstrap.sh
```

The bootstrap script installs the local development dependencies, builds the
SDK wheel, and seeds the vendored dependencies used by the tools.

## Run Tests

```bash
uv run --directory devflow-sdk --extra dev pytest
uv run --directory devflow-sdk --extra dev pytest ../devflow/
bash devflow-plugin-scaffold/tests/test_scaffold.sh
```

The example plugin has its own development commands:

```bash
cd smoke-check
just dev
just test
```

## Release

Detect and release all subprojects with unreleased changes:

```bash
bash scripts/release.sh
```

The release process:

1. Computes the next semver version for each changed subproject using
   Conventional Commits.
2. Releases `devflow-sdk` first, builds its wheel, creates a GitHub Release,
   and updates the vendored wheel in `devflow/`.
3. Releases `devflow` and updates the Homebrew formula.
4. Releases `devflow-plugin-scaffold`.
5. Syncs `homebrew-devflow/` to the standalone tap repository with
   `git subtree push`.

To release an individual subproject, run its release script directly:

```bash
(cd devflow-sdk && bash scripts/release.sh)
(cd devflow && bash scripts/release.sh devflow)
```

## Build a Plugin

Generate a ready-to-publish plugin repository:

```bash
curl -fsSL https://raw.githubusercontent.com/captainwonderwall/devflow-platform/main/devflow-plugin-scaffold/scaffold.sh \
  | bash -s -- my-format
```

The scaffold creates a plugin class, starter tests, install/uninstall
scripts, a release workflow, and a Homebrew formula template. See the
[`devflow-plugin-scaffold/README.md`](devflow-plugin-scaffold/README.md) for
the complete plugin interface and publishing options.

For a local example, see [`smoke-check/`](smoke-check/).

## Use the SDK in an External Repository

The SDK is distributed as a wheel attached to GitHub Releases, not through
PyPI. Download and vendor a release wheel with:

```bash
gh release download devflow-sdk/vX.Y.Z \
  --repo captainwonderwall/devflow-platform \
  --pattern "devflow_sdk-*.whl" \
  --dir vendor/
pip install vendor/devflow_sdk-*.whl
```

The SDK's plugin contract is documented in
[`devflow-sdk/README.md`](devflow-sdk/README.md).
