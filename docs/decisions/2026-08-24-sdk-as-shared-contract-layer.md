---
status: accepted
date: 2026-08-24
decision-makers: captainwonderwall
---

# Plugin contracts live in a standalone devflow-sdk package

## Context

Plugin authors need to import base classes to build plugins. Embedding them in the CLI couples authors to CLI internals.

## Decision

All plugin ABCs (`PluginBase`, `DraftPrPlugin`, `PluginLoaderBase`) live in `devflow-sdk`. The CLI provides the concrete `PluginLoader`. Authors depend only on the SDK.

## Consequences

- SDK versions independently from the CLI
- Missing abstract methods raise `TypeError` at instantiation
- New plugin types require a `devflow-sdk` release before authors can use them

## Implementation Plan

- **Paths**: `devflow-sdk/devflow_sdk/` (plugin_base, plugin_loader, plugin_registry, draft_pr_plugin), `devflow/plugin-manager/plugin_loader.py`
- **Follow**: new plugin types as ABCs in `devflow-sdk/devflow_sdk/`; new loader methods in `PluginLoaderBase` first
- **Avoid**: importing `devflow` CLI code from inside `devflow-sdk`; optional methods on ABCs

### Verification

- [ ] `pip install -e devflow-sdk/` pulls no `devflow` CLI code
- [ ] A `DraftPrPlugin` subclass missing an abstract method raises `TypeError` on instantiation
- [ ] `devflow/plugin-manager/plugin_loader.py` imports only from `devflow_sdk`
