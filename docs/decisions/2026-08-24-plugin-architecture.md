---
status: accepted
date: 2026-08-24
decision-makers: captainwonderwall
---

# Plugin architecture: path-based registry + importlib + Homebrew

## Context

Target audience is macOS developers installing via Homebrew. Plugins must be installable without Python knowledge. PyPI overhead is not justified at current scale.

## Decision

- Registry: `~/.devflow/plugin-registry.json` (versioned JSON, `fcntl` atomic locking)
- Loading: `importlib.util.spec_from_file_location` from registered path
- Distribution: Homebrew only
- Out of scope: Windows, inter-plugin sandboxing

## Consequences

- `brew install <plugin>` is the full install story — no pip required
- Plugins decouple from the CLI release cycle
- Registry locking is macOS/Linux only (`fcntl`)
- Plugins share the CLI process — no isolation

## Implementation Plan

- **Paths**: `devflow/plugin-manager/plugin_loader.py`, `devflow-sdk/devflow_sdk/`
- **Follow**: all registry writes via the internal `RegistryStore`; discovery via `PluginLoader.discover(BaseCls)`
- **Avoid**: direct writes to `~/.devflow/plugin-registry.json`; `pkg_resources` entry points

### Verification

- [ ] `scaffold.sh <name>` produces a plugin repo with a `DraftPrPlugin` subclass and Homebrew formula
- [ ] Homebrew-installed plugin is discoverable by `PluginLoader.discover(DraftPrPlugin)`
- [ ] Concurrent `register` calls do not corrupt the registry
