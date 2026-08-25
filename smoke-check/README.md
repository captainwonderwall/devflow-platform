# smoke-check

A [devflow](https://github.com/captainwonderwall/devflow) plugin for `draft-pr`.

## Install

```bash
bash install.sh
```

## Uninstall

```bash
bash uninstall.sh
```

## Prerequisites

Install once per machine:

```bash
brew install uv just
```

## Develop

Install dev dependencies (one-time per repo):

```bash
just dev
```

Run tests:

```bash
just test
```

If your plugin has runtime extras beyond devflow-sdk, add them to
`[project.dependencies]` in `pyproject.toml` and run:

```bash
just vendor
```

This downloads the wheels into `vendor/` — commit the result.

## Publish a release

1. Fill in `build_prompt` and `build_body` in `smoke_check.py`.
2. Run tests: `just test`.
3. Commit your changes, then run:
   ```bash
   bash scripts/release.sh
   ```
   This bumps the version, tags, and pushes. GitHub Actions runs tests and creates a GitHub release (the Homebrew formula downloads the source tarball directly from the tag).
