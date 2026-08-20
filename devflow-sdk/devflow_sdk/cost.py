import json
import re
import ssl
import threading
import urllib.request


class CostAccumulator:
    def __init__(self):
        self._total_usd = 0.0
        self._cad_rate = None
        self._thread = None
        self._printed = False

    def start_rate_fetch(self):
        self._thread = threading.Thread(target=self._fetch_rate, daemon=True)
        self._thread.start()

    def _fetch_rate(self):
        try:
            ctx = ssl.create_default_context()
            # Python 3.14 requires CA certs to have keyUsage; corporate proxy CAs often lack it
            ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
            # Corporate SSL-inspecting proxy (e.g. Netskope) returns 403 for the
            # default Python-urllib User-Agent; a normal browser-like UA passes.
            req = urllib.request.Request(
                "https://api.frankfurter.dev/v1/latest?from=USD&to=CAD",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(
                req,
                timeout=5,
                context=ctx,
            ) as resp:
                data = json.loads(resp.read())
                self._cad_rate = data["rates"]["CAD"]
        except Exception:
            self._cad_rate = None

    def add(self, usage: dict, model: str, pricing: dict) -> None:
        prices = pricing.get(re.sub(r'-\d{8}$', '', model))
        if not prices:
            return
        self._total_usd += (
            usage.get("input_tokens", 0) / 1_000_000 * prices["input"]
            + usage.get("output_tokens", 0) / 1_000_000 * prices["output"]
            + usage.get("cache_read_input_tokens", 0) / 1_000_000 * prices["cache_read"]
            + usage.get("cache_write_input_tokens", 0) / 1_000_000 * prices["cache_write"]
        )

    def print_summary(self):
        if self._printed:
            return
        self._printed = True
        if self._thread is not None:
            self._thread.join(timeout=5)
        usd = self._total_usd
        if self._cad_rate is not None:
            cad = usd * self._cad_rate
            print(f"\nCost: ${usd:.4f} USD / ${cad:.4f} CAD (rate: {self._cad_rate:.4f})")
        else:
            print(f"\nCost: ${usd:.4f} USD  (CAD conversion unavailable)")


accumulator = CostAccumulator()
