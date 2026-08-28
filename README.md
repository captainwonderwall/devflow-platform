# devflow

`devflow` is a set of AI-assisted command-line tools for moving an issue from
task tracker to merged change. It creates isolated worktrees, drafts pull
requests, addresses review feedback, squashes commits, and cleans up finished
work.

The tools are interactive: they show what they are about to do and ask for
confirmation before actions such as changing files, posting replies, pushing,
or removing a worktree.

## Install

Install the Homebrew tap and the toolchain:

```bash
brew tap captainwonderwall/devflow
brew install devflow
```

Install the integrations required by the workflows you use:

```bash
brew install worktrunk gh
brew tap atlassian/homebrew-acli && brew install acli
```

You also need an AI CLI configured for the provider selected in `devflow-config`.
The default supported provider is Claude; install it from
<https://claude.ai/code>.

After installing Homebrew packages, enable the shell integrations used to
switch worktrees automatically:

```bash
bash "$(brew --prefix)/opt/devflow/libexec/scripts/setup-shell.sh"
source ~/.zshrc  # use ~/.bashrc for Bash
```

Use `gh auth login` for GitHub issues and pull requests. Authenticate Jira's
`acli` separately if you use Jira issues.

## Configure devflow

Run the wizard whenever you want to create or update configuration:

```bash
devflow-config
```

Configuration is stored in `~/.devflow/config.json`. The wizard configures:

- The AI provider (`claude` or `opencode`)
- `fast` and `capable` model names and token pricing
- The default `draft-pr` plugin
- Optional path-based rules that select different plugins per project

Re-running the wizard preserves settings outside its managed fields. Plugins
are registered separately and can be inspected with:

```bash
devflow-plugin list
```

## Daily Workflow

Run the tools from the repository you are working on. A typical workflow is:

```text
start-issue -> edit and test -> draft-pr -> address-pr -> finish-issue
```

Use `squash-commits` before opening a pull request when your branch contains
several commits.

### 1. Start an issue

Create a branch and isolated worktree from a Jira key or GitHub issue number:

```bash
start-issue VDP-46625
start-issue 42
```

The issue metadata is fetched, a branch type is selected, and a worktree is
created. Use an explicit branch type when inference is not appropriate:

```bash
start-issue VDP-46625 --fix
start-issue 42 --feat
start-issue 42 --hotfix
start-issue 42 --chore
start-issue 42 --docs
```

Supported branch types are `feat`, `fix`, `hotfix`, `chore`, and `docs`.

### 2. Draft a pull request

From the issue worktree, run:

```bash
draft-pr
```

`draft-pr` gathers the branch and diff context, asks for issue and
customer-visibility details, lets you select a registered plugin, and uses
the configured capable model to draft the PR. It creates the PR through the
GitHub CLI. To supply a GitHub issue when it cannot be inferred from the
branch:

```bash
draft-pr --github-issue 42
```

If a PR already exists for the branch, the tool reports its URL instead of
creating a duplicate.

### 3. Address review comments

From the PR's worktree, run:

```bash
address-pr
```

The tool fetches unresolved review comments, uses AI to explain or group them,
lets you select which comments to address, applies the changes, and prepares
replies. It scopes commits to files changed during the session so unrelated
pre-existing work is not swept into the commit. Review and confirm replies
and the optional push interactively.

For additional diagnostics, preserve the AI provider's raw command output in
temporary debug files:

```bash
address-pr --debug
```

### 4. Squash commits

When the branch has multiple commits, run:

```bash
squash-commits
```

The tool drafts a single Conventional Commits-style message, handles a dirty
working tree through an interactive stash choice, and asks whether to
force-push with `--force-with-lease`. It does nothing when the branch has one
or zero commits ahead of its base branch.

### 5. Finish an issue

After the branch has been merged, remove its worktree and branch:

```bash
finish-issue VDP-46625
finish-issue 42
```

When run inside a worktree created by `start-issue`, the issue argument can be
omitted:

```bash
finish-issue
```

`finish-issue` verifies that the matching branch is merged before removing
anything. If the worktree is dirty, it asks whether to abort or discard the
uncommitted changes.

## Plugins

`draft-pr` supports plugins for different PR formats. Create a plugin with
the [plugin scaffold](devflow-plugin-scaffold/), install it, and verify it:

```bash
cd my-format
bash install.sh
devflow-plugin list
```

Select a default plugin or route projects by path with `devflow-config`.
Plugins can also be configured directly in `~/.devflow/config.json`:

```json
{
  "tools": {
    "draft-pr": {
      "plugin": {
        "default": "my-format",
        "rules": [
          { "paths": ["apps/web"], "plugin": "web-format" },
          { "paths": ["services/"], "plugin": "service-format" }
        ]
      }
    }
  }
}
```

Rules use the longest matching path relative to the Git root. If no rule
matches, `default` is used. If neither is set and multiple plugins are
registered, `draft-pr` prompts you to choose one.

## Troubleshooting

- If `start-issue` or `finish-issue` cannot switch directories, reload your
  shell after running the setup-shell script.
- If an issue cannot be fetched, verify `gh auth status` or your Jira `acli`
  authentication.
- If the AI call fails, verify the configured provider CLI works directly and
  re-run `devflow-config`.
- If `draft-pr` reports no plugins, install a plugin and check it with
  `devflow-plugin list`.

## Development

Contributor setup, tests, releases, SDK vendoring, and plugin-authoring
details are in [`DEVELOPMENT.md`](DEVELOPMENT.md).
