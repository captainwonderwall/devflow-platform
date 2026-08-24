# devflow-plugin-scaffold

One-liner scaffold for [devflow](https://github.com/captainwonderwall/devflow) plugin authors. Generates a ready-to-publish plugin repo from a single name argument.

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
  install.sh                ← copies plugin to devflow's plugins dir
  uninstall.sh              ← removes it
  scripts/
    release.sh              ← bumps version, tags, and pushes to trigger a release
  pyproject.toml            ← dev deps: devflow-sdk, pytest
  .github/
    workflows/
      release.yml           ← on git tag push, attaches .py to a GitHub Release
  README.md                 ← per-plugin usage and publish guide
  .gitignore
```

## Name rules

`<plugin-name>` must start with a lowercase letter and contain only lowercase letters, digits, and hyphens.

| Input | Module file | Class | Plugin name |
|-------|------------|-------|-------------|
| `acme-format` | `acme_format.py` | `AcmePlugin` | `"Acme Format"` |
| `acme` | `acme.py` | `AcmePlugin` | `"Acme"` |
| `my-org-format` | `my_org_format.py` | `MyPlugin` | `"My Org Format"` |

## Plugin interface

Fill in three methods in `<module>.py`:

```python
def get_questions(self, data: dict) -> list[dict]:
    # Return additional questions to ask the user before AI runs.
    # Each dict: {"id": str, "text": str}
    # Return [] if no extra questions needed.

def build_prompt(self, data: dict, user_inputs: dict) -> str:
    # Return the AI prompt string.
    # data: git_log, diff_stat, changed_files, branch, is_fix, ...
    # user_inputs: jira_ticket, github_issue, issue_type, customer_visible, + your get_questions answers

def build_body(self, ai_result: dict, user_inputs: dict) -> str:
    # Return the PR body markdown.
    # ai_result: whatever JSON keys your build_prompt requested
```

See [devflow-sdk](https://github.com/captainwonderwall/devflow-platform/tree/main/devflow-sdk) for the full `PluginBase` API.

## Publishing via Homebrew (public plugins)

1. Fill in `build_prompt` and `build_body`.
2. Run tests: `PYTHONPATH=. pytest tests/`.
3. Create a Homebrew tap repo (`acme-org/homebrew-tap`) with a formula:

```ruby
class DevflowPluginAcme < Formula
  desc "Acme PR format plugin for devflow"
  depends_on "captainwonderwall/devflow/devflow"

  def install
    (lib/"devflow/plugins").install "acme_format.py"
  end
end
```

4. Run `bash scripts/release.sh` to bump the version, tag, and push.
   GitHub Actions creates a release and attaches `acme_format.py`.
5. Users install: `brew tap acme-org/tap && brew install devflow-plugin-acme`.

## Publishing via direct download (private plugins)

1. Fill in `build_prompt` and `build_body`.
2. Run tests: `PYTHONPATH=. pytest tests/`.
3. Commit your changes, then run `bash scripts/release.sh`.
   GitHub Actions creates a release and attaches `acme_format.py`.
4. Users install by cloning the repo and running `bash install.sh`.
