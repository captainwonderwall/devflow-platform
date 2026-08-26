# devflow-platform

Monorepo for the devflow toolchain — a CLI for generating AI-assisted pull requests, with a plugin system for custom PR formats and an interactive wizard for configuration.

## Subprojects

| Directory | Description |
|-----------|-------------|
| [`devflow/`](devflow/) | The main CLI tool. Installed via Homebrew. |
| [`devflow-sdk/`](devflow-sdk/) | Shared plugin interface (`PluginBase`) and utilities. Distributed as a wheel attached to GitHub Releases. |
| [`devflow-plugin-scaffold/`](devflow-plugin-scaffold/) | One-liner scaffold for building new devflow plugins. |
| [`homebrew-devflow/`](homebrew-devflow/) | Homebrew tap formulae. Managed here via git subtree; synced to [`captainwonderwall/homebrew-devflow`](https://github.com/captainwonderwall/homebrew-devflow) on release. |

## Configuring devflow

devflow reads `~/.devflow/config.json`. Use the interactive wizard to create or update it:

```bash
devflow-config
```

The wizard walks through every setting pre-populated with your current values, so re-running it is how you update any setting.

**What it configures:**

- **AI provider** — choose between `claude` and `opencode`
- **Model tiers** — set the model name and token pricing for `fast` and `capable` tiers
- **draft-pr plugin routing** — set a default plugin and add path-based rules that map directories to specific plugins

**Example `~/.devflow/config.json`** (produced by the wizard):

```json
{
  "global": {
    "ai_provider": "claude",
    "models": {
      "fast": {
        "name": "claude-haiku-4-5-20251001",
        "pricing": { "input": 0.8, "output": 4.0, "cache_read": 0.08, "cache_write": 1.0 }
      },
      "capable": {
        "name": "claude-sonnet-4-6",
        "pricing": { "input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_write": 3.75 }
      }
    }
  },
  "tools": {
    "draft-pr": {
      "plugin": {
        "default": "smoke-check",
        "rules": [
          { "paths": ["/work/mobile"], "plugin": "mobile-format" }
        ]
      }
    }
  }
}
```

Any keys you add manually outside the wizard's scope are preserved on the next save.

## Getting started (contributors)

**Prerequisites:** [Homebrew](https://brew.sh), [GitHub CLI](https://cli.github.com)

```bash
git clone git@github.com:captainwonderwall/devflow-platform.git
cd devflow-platform
bash scripts/bootstrap.sh   # installs uv, builds SDK wheel, seeds vendor
```

Run tests:

```bash
uv run --no-project pytest devflow-sdk/   # SDK unit tests
uv run --no-project pytest devflow/       # devflow unit tests
bash devflow-plugin-scaffold/tests/test_scaffold.sh  # scaffold smoke test
```

## Releasing

Detect and release all subprojects that have unreleased changes:

```bash
bash scripts/release.sh
```

The script:
1. Computes the next semver version for each changed subproject using Conventional Commits.
2. Releases **devflow-sdk** first (builds a wheel, creates a GitHub Release, updates the vendor wheel in `devflow/`).
3. Releases **devflow** (bumps the Homebrew formula, tags `devflow/vX.Y.Z`).
4. Releases **devflow-plugin-scaffold** (bumps `VERSION`, tags `devflow-plugin-scaffold/vX.Y.Z`).
5. Syncs `homebrew-devflow/` to the standalone tap repo via `git subtree push`.

To release a single subproject only, run its own release script directly:

```bash
# SDK
(cd devflow-sdk && bash scripts/release.sh)

# devflow
(cd devflow && bash scripts/release.sh devflow)
```

## Using devflow-sdk in external repos

The SDK is distributed as a wheel attached to GitHub Releases — not published to PyPI. To vendor it:

```bash
gh release download devflow-sdk/vX.Y.Z \
  --repo captainwonderwall/devflow-platform \
  --pattern "devflow_sdk-*.whl" \
  --dir vendor/
pip install vendor/devflow_sdk-*.whl
```

See [`devflow-sdk/README.md`](devflow-sdk/README.md) for the full plugin interface.

## Creating a plugin

```bash
curl -fsSL https://raw.githubusercontent.com/captainwonderwall/devflow-platform/main/devflow-plugin-scaffold/scaffold.sh | bash -s -- my-format
```

See [`devflow-plugin-scaffold/README.md`](devflow-plugin-scaffold/README.md) for full instructions.

## Repository structure

```
devflow-platform/
├── devflow/                    # main CLI
│   ├── scripts/
│   │   ├── release.sh          # release devflow; updates Homebrew formula
│   │   └── update-vendor.sh    # downloads SDK wheel from GitHub Releases
│   └── vendor/                 # vendored devflow-sdk wheel
├── devflow-sdk/                # plugin SDK
│   └── scripts/
│       └── release.sh          # release SDK; attaches wheel to GitHub Release
├── devflow-plugin-scaffold/    # plugin scaffolding tool
│   └── scaffold.sh
├── homebrew-devflow/           # Homebrew formulae (git subtree)
├── scripts/
│   ├── bootstrap.sh            # one-time dev setup
│   └── release.sh              # top-level release orchestrator
└── .github/
    └── workflows/
        └── ci.yml              # unified CI (sdk-tests, devflow-tests, scaffold-tests)
```
