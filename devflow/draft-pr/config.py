from __future__ import annotations

from dataclasses import dataclass, field

from devflow_sdk.config import PluginConfig


@dataclass
class DirectoryRule:
    paths: list[str]
    plugin: str


@dataclass
class DraftPrConfig:
    plugin: PluginConfig[DirectoryRule] = field(default_factory=PluginConfig)

    def __post_init__(self):
        if isinstance(self.plugin, dict):
            raw_rules = self.plugin.get("rules", [])
            rules = [DirectoryRule(**r) for r in raw_rules]
            self.plugin = PluginConfig(
                default=self.plugin.get("default"),
                rules=rules,
            )
        self.plugin.rules.sort(
            key=lambda r: max((len(p) for p in r.paths), default=0),
            reverse=True,
        )

    def validate(self) -> None:
        if not self.plugin.rules and self.plugin.default is None:
            raise ValueError(
                "draft-pr: plugin config must have at least one rule or a default"
            )
        for rule in self.plugin.rules:
            if not rule.paths:
                raise ValueError(
                    "draft-pr: each plugin rule must have at least one path"
                )


def resolve_plugin(config: DraftPrConfig, cwd: str) -> str | None:
    for rule in config.plugin.rules:
        if any(cwd.startswith(p) for p in rule.paths):
            return rule.plugin
    return config.plugin.default
