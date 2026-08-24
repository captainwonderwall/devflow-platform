---
status: accepted
date: 2026-08-24
decision-makers: captainwonderwall
---

# Sync homebrew tap via PR instead of direct push

## Context

`scripts/release.sh` originally called `git subtree push --prefix=homebrew-devflow tap main` to sync the `homebrew-devflow/` subtree to the separate [`captainwonderwall/homebrew-devflow`](https://github.com/captainwonderwall/homebrew-devflow) tap repository. The tap repo has branch protection requiring all changes to go through a pull request, so direct push to `main` is blocked.

## Decision

On `devflow` release, push the subtree to a `release/devflow-vX.Y.Z` branch on the tap remote and open a PR via `gh pr create`. The `tap` git remote must be configured locally (`git remote add tap https://github.com/captainwonderwall/homebrew-devflow.git`); the script fails fast with the exact command if the remote is missing.

Out of scope: auto-merging the PR, CI on the tap repo.

## Consequences

- Compatible with branch protection — no bypass required
- Tap update requires a PR merge before `brew upgrade devflow` picks it up (small delay, manual step)
- `tap` remote must be present in every local clone used for releasing; the script's preflight check makes this self-documenting

## Implementation Plan

- **Affected path**: `scripts/release.sh` — preflight check (before confirm prompt) and sync step at end of file
- **Pattern**: `git subtree push --prefix=homebrew-devflow "$TAP_REMOTE" "$TAP_BRANCH"` then `gh pr create --repo captainwonderwall/homebrew-devflow --base main --head "$TAP_BRANCH"`
- **Avoid**: `git subtree push ... tap main` (direct push to main)

### Verification

- [ ] `scripts/release.sh` exits with a clear error message when the `tap` remote is not configured
- [ ] A `devflow` release creates a `release/devflow-vX.Y.Z` branch on `captainwonderwall/homebrew-devflow` and opens a PR targeting `main`
- [ ] No direct push to `main` on the tap repo occurs during release
