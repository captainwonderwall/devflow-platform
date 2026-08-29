# devflow-sdk

Shared utilities and plugin interface for [devflow](https://github.com/captainwonderwall/devflow-platform/tree/main/devflow).

## Install

The SDK is distributed as a wheel attached to GitHub Releases. Download and install it:

```bash
gh release download devflow-sdk/vX.Y.Z \
  --repo captainwonderwall/devflow-platform \
  --pattern "devflow_sdk-*.whl" \
  --dir vendor/
pip install vendor/devflow_sdk-*.whl
```

Replace `vX.Y.Z` with the version you need. To find the latest:

```bash
gh release list --repo captainwonderwall/devflow-platform | grep devflow-sdk
```

## Plugin interface

Subclass `DraftPrPlugin` to build a devflow plugin:

```python
from devflow_sdk.core.plugin import DraftPrPlugin

class MyPlugin(DraftPrPlugin):
    name = "My Format"

    def get_questions(self, data: dict) -> list[dict]:
        return []

    def build_prompt(self, data: dict, user_inputs: dict) -> str:
        return f"Summarise: {data['git_log']}"

    def build_body(self, ai_result: dict, user_inputs: dict) -> str:
        return f"## {ai_result['title']}\n\n{ai_result['description']}\n"
```

See [devflow-plugin-scaffold](https://github.com/captainwonderwall/devflow-platform/tree/main/devflow-plugin-scaffold) to generate a plugin repo.
