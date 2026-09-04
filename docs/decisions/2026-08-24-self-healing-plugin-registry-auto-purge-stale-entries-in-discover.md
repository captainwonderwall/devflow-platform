---
status: accepted
date: 2026-08-24
decision-makers: captainwonderwall
---

# Self-healing plugin registry: auto-purge stale entries in discover()

## Context and Problem Statement

Homebrew formulas have no `uninstall_formula` DSL hook. When a user runs `brew uninstall devflow-plugin-<name>`, Homebrew removes the plugin's `.py` file from disk but has no mechanism to notify devflow. The entry in `~/.devflow/plugin-registry.json` therefore persists after uninstall. On the next `devflow draft-pr`, `PluginLoader.discover()` encounters a registry entry whose path is no longer a regular file.

The scaffold's formula template currently works around this with a comment asking users to manually run `devflow-plugin unregister <name>` before uninstalling — a step that is easy to miss and not enforced by Homebrew.

## Decision

Modify `PluginLoader.discover()` to call the internal `RegistryStore.purge_missing()`, which checks `Path.is_file()` for each registry entry. Missing or non-regular entries are collected and the registry is atomically rewritten before discovery proceeds. The registry becomes eventually consistent: stale entries are purged on the next `devflow draft-pr` run with no user action.

Non-goals: proactive filesystem monitoring, Windows/Linux support, a new CLI subcommand for cleanup.

## Consequences

- Good, because uninstall just works — no user action or documentation required
- Good, because the registry self-corrects even if a plugin file is accidentally deleted or moved
- Bad, because a stale entry persists until the next `discover()` call (acceptable — nothing breaks in the interim, the entry is simply skipped)
- Bad, because silent purges are harder to audit (mitigated: log a warning per removed entry)

## Implementation Plan

- **Affected paths**:
  - `devflow/plugin-manager/plugin_loader.py` — `PluginLoader.discover()`
  - `devflow-plugin-scaffold/scaffold.sh` — formula template comment
  - `devflow-plugin-scaffold/tests/test_scaffold.sh` — assertion on formula template

- **Patterns to follow**:
  - Reuse `RegistryStore`'s locked atomic write — do not write the registry file directly
  - Emit a `logging.warning` for each purged entry (consistent with how `unregister` logs)
  - Collect all missing entries first, then write once — not one write per missing entry

- **Patterns to avoid**:
  - Do not raise an exception on a missing path — `discover()` must remain non-fatal
  - Do not add a new CLI subcommand; cleanup is implicit

### Verification

- [ ] After `brew uninstall devflow-plugin-<name>` (or manual `rm` of the `.py`), the next `devflow draft-pr` run removes the stale entry from `~/.devflow/plugin-registry.json` with no error
- [ ] A warning is logged for each purged entry
- [ ] Concurrent `discover()` calls do not corrupt the registry (existing locking tests still pass)
- [ ] `devflow-plugin-scaffold/tests/test_scaffold.sh` asserts the formula template no longer contains the manual `devflow-plugin unregister` comment

## Alternatives Considered

- **`devflow-plugin gc` command**: explicit garbage-collect subcommand that scans and prunes missing entries. Rejected because it requires user action and documentation; the self-healing approach is invisible and always correct.
- **Sentinel file**: formula installs a sentinel alongside the `.py`; devflow watches the sentinel. Rejected because it adds indirection with no benefit over checking the `.py` path directly.

## More Information

- Supersedes the manual-unregister comment in `devflow-plugin-scaffold/scaffold.sh` formula template
- Related ADRs: [Plugin architecture](2026-08-24-plugin-architecture.md), [Homebrew distribution](2026-08-24-homebrew-distribution.md)
- GitHub issue: captainwonderwall/devflow-platform (to be linked once created)
- Revisit if: Homebrew adds a real `post_uninstall` hook, or devflow gains a filesystem-watching daemon
