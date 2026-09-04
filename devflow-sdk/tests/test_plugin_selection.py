from collections.abc import Mapping

import pytest

from devflow_sdk.plugin.plugin_selection import select_plugin


def test_empty_plugins_returns_none() -> None:
    assert select_plugin({}) is None


def test_single_plugin_is_selected_without_prompt() -> None:
    plugin = object()

    assert select_plugin({"only": plugin}) is plugin


def test_configured_plugin_wins_without_prompt() -> None:
    first = object()
    second = object()

    assert select_plugin({"first": first, "second": second}, "second") is second


def test_unknown_configured_plugin_warns_and_prompts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    first = object()
    second = object()
    monkeypatch.setattr("devflow_sdk.plugin.plugin_selection.select", lambda message, choices: "first")

    assert select_plugin({"first": first, "second": second}, "missing") is first
    assert "configured plugin 'missing' not found" in capsys.readouterr().err


def test_prompt_cancellation_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("devflow_sdk.plugin.plugin_selection.select", lambda message, choices: None)

    assert select_plugin({"first": object(), "second": object()}) is None
