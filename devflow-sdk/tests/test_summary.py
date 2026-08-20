

from devflow_sdk.summary import Summary
from devflow_sdk.ai_providers.claude_provider import ClaudeProvider

_CLAUDE = ClaudeProvider.pricing


def test_items_appear_in_output(capsys):
    s = Summary()
    s.add("Commit", "abc1234")
    s.add("PR", "https://github.com/foo/bar/pull/42")
    s._cost._cad_rate = None
    s.print_summary()
    out = capsys.readouterr().out
    assert "Commit" in out
    assert "abc1234" in out
    assert "PR" in out
    assert "https://github.com/foo/bar/pull/42" in out


def test_cost_row_appears(capsys):
    s = Summary()
    s.add_cost({"input_tokens": 1_000_000}, "claude-haiku-4-5", _CLAUDE)
    s._cost._cad_rate = None
    s.print_summary()
    out = capsys.readouterr().out
    assert "Cost" in out
    assert "$1.0000 USD" in out


def test_cost_with_cad_rate(capsys):
    s = Summary()
    s.add_cost({"input_tokens": 1_000_000}, "claude-haiku-4-5", _CLAUDE)
    s._cost._cad_rate = 1.36
    s.print_summary()
    out = capsys.readouterr().out
    assert "$1.0000 USD" in out
    assert "CAD" in out
    assert "1.3600" in out


def test_cost_unavailable_message(capsys):
    s = Summary()
    s._cost._cad_rate = None
    s.print_summary()
    out = capsys.readouterr().out
    assert "CAD conversion unavailable" in out


def test_bordered_box_unicode_chars(capsys):
    s = Summary()
    s._cost._cad_rate = None
    s.print_summary()
    out = capsys.readouterr().out
    for char in ("┌", "┐", "└", "┘", "─", "│", "├", "┤"):
        assert char in out, f"Missing box char: {char}"


def test_summary_header_in_box(capsys):
    s = Summary()
    s._cost._cad_rate = None
    s.print_summary()
    out = capsys.readouterr().out
    assert "Summary" in out


def test_idempotent(capsys):
    s = Summary()
    s._cost._cad_rate = None
    s.print_summary()
    s.print_summary()
    out = capsys.readouterr().out
    assert out.count("Summary") == 1


def test_no_items_renders_cost_only(capsys):
    s = Summary()
    s._cost._cad_rate = None
    s.print_summary()
    out = capsys.readouterr().out
    assert "Cost" in out
    assert "$0.0000 USD" in out


def test_cost_is_last_data_row(capsys):
    s = Summary()
    s.add("PR", "https://example.com")
    s._cost._cad_rate = None
    s.print_summary()
    out = capsys.readouterr().out
    data_rows = [
        line for line in out.splitlines()
        if "│" in line and "Summary" not in line
        and "├" not in line and "┤" not in line
        and "┌" not in line and "└" not in line
    ]
    assert len(data_rows) == 2
    assert "Cost" in data_rows[-1]


def test_all_rows_same_width(capsys):
    s = Summary()
    s.add("Short", "x")
    s.add("A very long key indeed", "and a very long value too for this row")
    s._cost._cad_rate = None
    s.print_summary()
    out = capsys.readouterr().out
    box_lines = [line for line in out.splitlines() if line.startswith("│")]
    widths = {len(line) for line in box_lines}
    assert len(widths) == 1, f"Inconsistent row widths: {widths}"


def test_module_singleton_shares_cost_accumulator():
    from devflow_sdk.summary import summary
    from devflow_sdk.cost import accumulator
    assert summary._cost is accumulator
