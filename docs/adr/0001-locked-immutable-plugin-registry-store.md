---
status: accepted
date: 2026-09-04
---

# Use a locked immutable plugin registry store

The plugin registry will be concentrated behind an internal `RegistryStore` module at `devflow_sdk.plugin.registry_store`. It provides locked immutable snapshots, operation-specific atomic mutations, and a single locked purge operation; `PluginLoader` remains the public interface and constructs the store from its existing registry path.

## Considered Options

- **Strict persisted-data errors:** malformed data raises `MalformedRegistryError`, filesystem failures raise `RegistryIOError`, and invalid registration raises `InvalidRegistrationError`; all propagate through callers and share `RegistryError`.
- **Non-destructive filesystem policy:** missing registries are empty until mutation, while symlinked or non-regular registry and lock paths are rejected. Lock files use `0600`; new registries use `0600`; existing registry permissions are preserved.
- **Durability and concurrency:** reads use shared locks; mutations reload under an exclusive lock, `fsync()` temporary files, and atomically rename. Lock acquisition blocks, with no callbacks or plugin loading while locked.
- **Forward compatibility:** unknown JSON fields are retained as opaque deep-copied metadata across rewrites; removed entries discard their metadata.

## Consequences

`PluginEntry` becomes frozen and snapshots use `MappingProxyType`, so callers cannot mutate registry state outside the seam. Existing private persistence helpers are removed rather than retained as a second implementation. Tests target the `RegistryStore` interface, including separate-process concurrency and patched `fsync()`/rename failures; loader tests focus on delegation and runtime behavior.
