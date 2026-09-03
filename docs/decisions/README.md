# Architecture Decision Records

Decisions that shaped how devflow is built and distributed. Each ADR captures context, alternatives considered, and the rationale behind the choice — so future contributors (human or agent) can understand the why, not just the what.

## Index

| Date | Title | Status |
|------|-------|--------|
| 2026-08-24 | [Adopt path-based plugin architecture with Homebrew distribution](2026-08-24-plugin-architecture.md) | accepted |
| 2026-08-24 | [Extract plugin contracts into a standalone devflow-sdk package](2026-08-24-sdk-as-shared-contract-layer.md) | accepted |
| 2026-08-24 | [Use Homebrew as the sole plugin distribution channel](2026-08-24-homebrew-distribution.md) | accepted |
| 2026-08-24 | [Self-healing plugin registry: auto-purge stale entries in discover()](2026-08-24-self-healing-plugin-registry-auto-purge-stale-entries-in-discover.md) | accepted |
| 2026-08-24 | [Sync homebrew tap via PR instead of direct push](2026-08-24-homebrew-tap-sync-via-pr.md) | accepted |

## Conventions

- Filenames: `YYYY-MM-DD-short-slug.md`
- Statuses: `proposed` → `accepted` or `rejected` → optionally `deprecated` or `superseded by [title](file.md)`
- When superseding an ADR: update the old one's status, create a new ADR that links back to it
