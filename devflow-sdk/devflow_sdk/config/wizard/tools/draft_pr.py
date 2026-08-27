from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

from devflow_sdk.config.schema import DevflowConfig, PluginConfig
from devflow_sdk.config.wizard import WizardStep
from devflow_sdk.plugin.plugin_loader_impl import PluginLoader
from devflow_sdk.prompts import Choice, checkbox, confirm, select, text


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
        if any(cwd == p.rstrip("/") or cwd.startswith(p.rstrip("/") + "/") for p in rule.paths):
            return rule.plugin
    return config.plugin.default


def _rules_to_dicts(rules: list[DirectoryRule]) -> list[dict]:
    return [{"paths": r.paths, "plugin": r.plugin} for r in rules]


class DraftPrWizardStep(WizardStep):
    section = "draft-pr: Plugin Routing"
    tool_name = "draft-pr"
    schema_cls = DraftPrConfig

    def run(self, current: DevflowConfig) -> DevflowConfig:
        loader = PluginLoader()
        available = loader.list_plugins()
        if not available:
            print("  No plugins registered — skipping draft-pr plugin routing configuration.")
            return current

        plugin_names = list(available.keys())

        # Load existing draft-pr config
        raw_draft_pr = current.tools.get("draft-pr", {})
        raw_plugin = raw_draft_pr.get("plugin", {})
        current_default = raw_plugin.get("default")
        current_rules: list[DirectoryRule] = [
            DirectoryRule(**r) for r in raw_plugin.get("rules", [])
        ]

        # Select default plugin
        default_choices = [
            Choice(name, checked=(name == current_default))
            for name in plugin_names
        ]
        chosen_default = select("Default plugin for draft-pr:", choices=default_choices)
        if chosen_default is None:
            return current

        # Show existing rules; user picks which to keep
        kept_rules: list[DirectoryRule] = []
        if current_rules:
            rule_choices = [
                Choice(
                    f"{', '.join(r.paths)} → {r.plugin}",
                    value=r,
                    checked=True,
                )
                for r in current_rules
            ]
            answer = checkbox("Which path rules should be kept?", choices=rule_choices, allow_empty=True)
            if answer is None:
                return current  # user cancelled; leave config unchanged
            kept_rules = answer  # may be [] if user deliberately deselected all

        # Offer to add new rules
        while confirm("Add a new path rule?", default=False):
            raw_paths = text("Path patterns (comma-separated):")
            if not raw_paths:
                break
            paths = [p.strip() for p in raw_paths.split(",") if p.strip()]
            rule_plugin_choices = [
                Choice(name, checked=(name == chosen_default))
                for name in plugin_names
            ]
            rule_plugin = select("Plugin for this path:", choices=rule_plugin_choices)
            if rule_plugin and paths:
                kept_rules.append(DirectoryRule(paths=paths, plugin=rule_plugin))

        updated_tools = {
            **current.tools,
            "draft-pr": {
                **raw_draft_pr,
                "plugin": {
                    "default": chosen_default,
                    "rules": _rules_to_dicts(kept_rules),
                },
            },
        }
        return dataclasses.replace(current, tools=updated_tools)
