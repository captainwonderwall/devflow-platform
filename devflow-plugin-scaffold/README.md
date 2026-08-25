# devflow-plugin-scaffold

One-liner scaffold for [devflow](https://github.com/captainwonderwall/devflow) plugin authors. Generates a ready-to-publish plugin repo from a single name argument.

## Requirements

- Python >= 3.11
- [devflow](https://github.com/captainwonderwall/devflow) installed

## Usage

```bash
curl -fsSL https://raw.githubusercontent.com/captainwonderwall/devflow-platform/main/devflow-plugin-scaffold/scaffold.sh | bash -s -- acme-format
```

Or clone and run locally:

```bash
git clone https://github.com/captainwonderwall/devflow-platform
bash devflow-platform/devflow-plugin-scaffold/scaffold.sh acme-format
```

## What gets generated

Running `scaffold.sh acme-format` creates:

```
acme-format/
  acme_format.py            ← stubbed DraftPrPlugin subclass (fill this in)
  tests/
    test_acme_format.py     ← 4 starter tests, no AI required
  install.sh                ← registers plugin with devflow
  uninstall.sh              ← unregisters it
  scripts/
    release.sh              ← bumps version, tags, and pushes to trigger a release
  pyproject.toml            ← dev deps: devflow-sdk, pytest
  .github/
    workflows/
      release.yml           ← on git tag push, runs tests and creates a GitHub Release
  README.md                 ← per-plugin usage and publish guide
  .gitignore
  Formula/
    devflow-plugin-acme-format.rb  ← Homebrew formula template
```

## Name rules

`<plugin-name>` must start with a lowercase letter and contain only lowercase letters, digits, and hyphens.

| Input | Module file | Class | Plugin name |
|-------|------------|-------|-------------|
| `acme-format` | `acme_format.py` | `AcmePlugin` | `"Acme Format"` |
| `acme` | `acme.py` | `AcmePlugin` | `"Acme"` |
| `my-org-format` | `my_org_format.py` | `MyPlugin` | `"My Org Format"` |

## Install the SDK

`devflow-sdk` is not published to PyPI. Download the latest `.whl` from the [devflow-platform releases](https://github.com/captainwonderwall/devflow-platform/releases) and install it into your dev environment:

```bash
pip install devflow_sdk-<version>-py3-none-any.whl
```

Then install the remaining dev dependencies:

```bash
pip install pytest
```

## Plugin interface

A plugin is a single `.py` file containing a class that:

1. Inherits from `devflow_sdk.draft_pr_plugin.DraftPrPlugin`
2. Declares a `name` class attribute — the display name shown in the plugin picker
3. Implements three methods

```python
from devflow_sdk.draft_pr_plugin import DraftPrPlugin


class AcmePlugin(DraftPrPlugin):
    name = "Acme Format"

    def get_questions(self, data: dict) -> list[dict]:
        # Return additional questions to ask the user before the AI runs.
        # Each dict must have:
        #   id   — becomes the key for this answer in user_inputs
        #   text — shown to the user
        # Return [] if no extra questions are needed.
        return []

    def build_prompt(self, data: dict, user_inputs: dict) -> str:
        # Build and return the raw AI prompt string.
        # The prompt should instruct the AI to return a JSON object;
        # whatever keys you request here are what build_body receives in ai_result.
        return (
            "Output ONLY a JSON object with keys title and description:\n"
            + data["git_log"]
        )

    def build_body(self, ai_result: dict, user_inputs: dict) -> str:
        # Render and return the PR body as a markdown string.
        # ai_result is the parsed JSON dict returned by the AI.
        return f"## {ai_result['title']}\n\n{ai_result['description']}\n"
```

### `data` keys

`data` is passed to all three methods and contains information about the current branch and diff:

| Key | Type | Description |
|-----|------|-------------|
| `branch` | `str` | Current git branch name |
| `base` | `str` | Default branch (e.g. `"main"`) |
| `prefix` | `str \| None` | Branch type prefix (e.g. `fix`, `feat`, `chore`) |
| `jira_ticket` | `str \| None` | Jira key parsed from the branch name (e.g. `"VDP-123"`) |
| `github_issue` | `str \| None` | GitHub issue number parsed from the branch name |
| `issue_type` | `str \| None` | `"Issue"`, `"Feature"`, `"Enhancement"`, or `"Other"` |
| `is_fix` | `bool` | `True` if the prefix is `fix`, `bugfix`, or `hotfix` |
| `git_log` | `str` | `git log --oneline` from `origin/<base>..HEAD` |
| `diff_stat` | `str` | `git diff --stat` from `origin/<base>..HEAD` |
| `changed_files` | `list[str]` | Paths of all changed files |
| `behind_count` | `int` | How many commits the branch is behind `origin/<base>` |

### `user_inputs` keys

`user_inputs` is passed to `build_prompt` and `build_body` and contains answers to the standard devflow prompts plus any answers from `get_questions`:

| Key | Type | Description |
|-----|------|-------------|
| `jira_ticket` | `str \| None` | Jira ticket key entered by the user |
| `github_issue` | `str \| None` | GitHub issue number entered by the user |
| `issue_type` | `str` | `"Issue"`, `"Feature"`, `"Enhancement"`, or `"Other"` |
| `customer_visible` | `str` | `"yes"` or `"no"` |
| *(your ids)* | `str` | Answers to questions returned by `get_questions` |

### `ai_result`

`build_body` receives `ai_result`, which is the parsed JSON dict the AI returned in response to your `build_prompt`. The shape is entirely determined by the JSON keys you ask for in your prompt — there is no fixed schema.

## Register and activate the plugin

After generating the scaffold, register it with devflow:

```bash
cd acme-format
bash install.sh
```

This runs `devflow-plugin register acme-format /absolute/path/to/acme_format.py` and adds the plugin to `~/.devflow/plugin-registry.json`.

To verify it is registered:

```bash
devflow-plugin list
```

To remove it:

```bash
bash uninstall.sh
```

## Configure which plugin to use

devflow selects a plugin based on `~/.devflow/config.json`. Set a default, or apply path-based rules:

```json
{
  "tools": {
    "draft-pr": {
      "plugin": {
        "default": "acme-format",
        "rules": [
          { "paths": ["apps/web"], "plugin": "web-format" },
          { "paths": ["services/"], "plugin": "service-format" }
        ]
      }
    }
  }
}
```

Rules are matched longest-path-first against the current working directory relative to the git root. If no rule matches, `default` is used. If neither is configured and multiple plugins are registered, devflow prompts you to choose interactively.

## Run tests

```bash
PYTHONPATH=. pytest tests/
```

## Publishing via Homebrew (public plugins)

1. Fill in `build_prompt` and `build_body`.
2. Run tests: `PYTHONPATH=. pytest tests/`.
3. Create a Homebrew tap repo (`acme-org/homebrew-tap`) and add the generated formula from `Formula/devflow-plugin-acme-format.rb`, filling in the `url` and `sha256` after your first release.
4. Run `bash scripts/release.sh` to bump the version, tag, and push.
   GitHub Actions runs tests and creates a GitHub Release from the source tarball.
5. Update the formula `url` and `sha256` with the release tarball URL and its SHA256.
6. Users install: `brew tap acme-org/tap && brew install devflow-plugin-acme-format`.

## Publishing via direct download (private plugins)

1. Fill in `build_prompt` and `build_body`.
2. Run tests: `PYTHONPATH=. pytest tests/`.
3. Commit your changes, then run `bash scripts/release.sh`.
   GitHub Actions runs tests and creates a GitHub Release.
4. Users install by cloning the repo and running `bash install.sh`.
