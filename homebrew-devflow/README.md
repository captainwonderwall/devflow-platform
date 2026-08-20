# homebrew-devflow

Homebrew tap for [devflow](https://github.com/captainwonderwall/devflow) — AI-powered developer workflow scripts.

## Prerequisites

```bash
# Required for all tools
brew install gh
brew install worktrunk
# Install Claude Code from https://claude.ai/code

# Required for Jira integration
brew tap atlassian/homebrew-acli && brew install acli

# Authenticate
gh auth login
acli jira token create
```

## Install

```bash
brew tap captainwonderwall/devflow
brew install devflow
```

This installs: `draft-pr`, `address-pr`, `finish-issue`, `squash-commits`, `start-issue`.

## Install a plugin

Clone the plugin repo and run its install script:

```bash
git clone git@github.com:<org>/<plugin-repo>.git
bash <plugin-repo>/install.sh
```

## Set up shell integrations

`start-issue` and `finish-issue` need a one-time shell setup to switch your working directory:

```bash
bash $(brew --prefix)/opt/devflow/libexec/scripts/setup-shell.sh
source ~/.zshrc   # or ~/.bashrc
```

## Usage

```bash
start-issue VDP-46625    # start a Jira issue → creates branch + worktree
start-issue 42           # start a GitHub issue

draft-pr                 # AI-generates PR body and opens the PR
address-pr               # fetch review comments → AI applies fixes
squash-commits           # AI-drafts a squash commit message, force-pushes

finish-issue VDP-46625   # after PR is merged → cleans up the worktree
```

## Upgrade

```bash
brew upgrade devflow
```

After upgrading, reinstall any plugins (Homebrew does not preserve the plugins directory across formula upgrades). From each plugin's repo, run:

```bash
bash install.sh
```

## Add a third-party plugin

Third-party plugins are `.py` files placed in `$(brew --prefix)/lib/devflow/plugins/`. See [devflow-plugin-scaffold](https://github.com/captainwonderwall/devflow-plugin-scaffold) to generate a publishable plugin repo.

## Uninstall

```bash
brew uninstall devflow
brew untap captainwonderwall/devflow
```
