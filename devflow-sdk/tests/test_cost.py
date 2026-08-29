import json
import ssl
from io import BytesIO
from unittest.mock import patch


from devflow_sdk.core.cost import CostAccumulator
from devflow_sdk.core.ai.providers.claude_provider import ClaudeProvider
from devflow_sdk.core.ai.providers.opencode_provider import OpenCodeProvider

_CLAUDE = ClaudeProvider.pricing
_OPENCODE = OpenCodeProvider.pricing


def test_haiku_input_cost():
    acc = CostAccumulator()
    acc.add({"input_tokens": 1_000_000}, "claude-haiku-4-5", _CLAUDE)
    assert abs(acc._total_usd - 1.00) < 1e-9


def test_sonnet_output_cost():
    acc = CostAccumulator()
    acc.add({"output_tokens": 1_000_000}, "claude-sonnet-4-6", _CLAUDE)
    assert abs(acc._total_usd - 15.00) < 1e-9


def test_cache_read_cost():
    acc = CostAccumulator()
    acc.add({"cache_read_input_tokens": 1_000_000}, "claude-sonnet-4-6", _CLAUDE)
    assert abs(acc._total_usd - 0.30) < 1e-9


def test_cache_write_cost():
    acc = CostAccumulator()
    acc.add({"cache_write_input_tokens": 1_000_000}, "claude-haiku-4-5", _CLAUDE)
    assert abs(acc._total_usd - 1.25) < 1e-9


def test_accumulates_multiple_calls():
    acc = CostAccumulator()
    acc.add({"input_tokens": 500_000}, "claude-haiku-4-5", _CLAUDE)
    acc.add({"input_tokens": 500_000}, "claude-haiku-4-5", _CLAUDE)
    assert abs(acc._total_usd - 1.00) < 1e-9


def test_mixed_models():
    acc = CostAccumulator()
    acc.add({"input_tokens": 1_000_000}, "claude-haiku-4-5", _CLAUDE)
    acc.add({"input_tokens": 1_000_000}, "claude-sonnet-4-6", _CLAUDE)
    assert abs(acc._total_usd - 4.00) < 1e-9


def test_unknown_model_is_zero():
    acc = CostAccumulator()
    acc.add({"input_tokens": 1_000_000}, "unknown-model", _CLAUDE)
    assert acc._total_usd == 0.0


def test_empty_usage_is_zero():
    acc = CostAccumulator()
    acc.add({}, "claude-haiku-4-5", _CLAUDE)
    assert acc._total_usd == 0.0


def test_print_summary_usd_only(capsys):
    acc = CostAccumulator()
    acc.add({"input_tokens": 1_000_000}, "claude-haiku-4-5", _CLAUDE)
    acc._cad_rate = None
    acc.print_summary()
    out = capsys.readouterr().out
    assert "$1.0000 USD" in out
    assert "CAD conversion unavailable" in out


def test_print_summary_with_cad(capsys):
    acc = CostAccumulator()
    acc.add({"input_tokens": 1_000_000}, "claude-haiku-4-5", _CLAUDE)
    acc._cad_rate = 1.36
    acc.print_summary()
    out = capsys.readouterr().out
    assert "$1.0000 USD" in out
    assert "CAD" in out
    assert "1.3600" in out


def test_fetch_rate_sets_browser_user_agent_and_relaxed_ssl():
    fake_response = BytesIO(json.dumps({"rates": {"CAD": 1.42}}).encode())

    class _CtxManager:
        def __enter__(self):
            return fake_response

        def __exit__(self, *args):
            return False

    with patch("devflow_sdk.core.cost.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _CtxManager()

        acc = CostAccumulator()
        acc._fetch_rate()

        assert mock_urlopen.called
        _, kwargs = mock_urlopen.call_args
        req = mock_urlopen.call_args[0][0]

        assert req.get_header("User-agent") == "Mozilla/5.0"
        assert req.full_url == "https://api.frankfurter.dev/v1/latest?from=USD&to=CAD"

        ctx = kwargs["context"]
        assert not (ctx.verify_flags & ssl.VERIFY_X509_STRICT)

    assert acc._cad_rate == 1.42


def test_fetch_rate_handles_failure():
    with patch("devflow_sdk.core.cost.urllib.request.urlopen", side_effect=OSError("blocked")):
        acc = CostAccumulator()
        acc._fetch_rate()
        assert acc._cad_rate is None


def test_add_with_opencode_pricing():
    acc = CostAccumulator()
    opencode_model = next(iter(_OPENCODE))
    price = _OPENCODE[opencode_model]["input"]
    acc.add({"input_tokens": 1_000_000}, opencode_model, _OPENCODE)
    assert abs(acc._total_usd - price) < 1e-9


def test_add_empty_pricing_is_zero():
    acc = CostAccumulator()
    acc.add({"input_tokens": 1_000_000}, "claude-haiku-4-5", {})
    assert acc._total_usd == 0.0


def test_add_treats_missing_cache_write_price_as_zero():
    acc = CostAccumulator()
    pricing = {
        "github-copilot/gpt-5.6-luna": {
            "input": 0.2,
            "output": 1.2,
            "cache_read": 0.02,
            "cache_write": None,
        }
    }

    acc.add(
        {"input_tokens": 1_000_000, "cache_write_input_tokens": 1_000_000},
        "github-copilot/gpt-5.6-luna",
        pricing,
    )

    assert abs(acc._total_usd - 0.2) < 1e-9


def test_pricing_matches_provider_pricing_tables():
    assert "claude-haiku-4-5" in _CLAUDE
    assert "claude-sonnet-4-6" in _CLAUDE
    assert any("claude-sonnet" in k for k in _OPENCODE)
