from devflow_sdk.cost import CostAccumulator, accumulator as _shared_accumulator


class Summary:
    def __init__(self, cost: CostAccumulator = None):
        self._items = []
        self._cost = cost if cost is not None else CostAccumulator()
        self._printed = False

    def start_rate_fetch(self):
        self._cost.start_rate_fetch()

    def add(self, key: str, value: str) -> None:
        self._items.append((key, value))

    def add_cost(self, usage: dict, model: str, pricing: dict) -> None:
        self._cost.add(usage, model, pricing)

    def _format_cost(self) -> str:
        usd = self._cost._total_usd
        rate = self._cost._cad_rate
        if rate is not None:
            cad = usd * rate
            return f"${usd:.4f} USD / ${cad:.4f} CAD (rate: {rate:.4f})"
        return f"${usd:.4f} USD (CAD conversion unavailable)"

    def print_summary(self) -> None:
        if self._printed:
            return
        self._printed = True
        if self._cost._thread is not None:
            self._cost._thread.join(timeout=5)

        rows = list(self._items) + [("Cost", self._format_cost())]
        key_col = max(len(k) for k, _ in rows)
        val_col = max(len(v) for _, v in rows)

        bar = "─" * (key_col + val_col + 4)
        print("\n┌" + bar + "┐")
        print("│ " + "Summary".ljust(key_col + val_col + 2) + " │")
        print("├" + bar + "┤")
        for key, val in rows:
            print("│ " + key.ljust(key_col) + "  " + val.ljust(val_col) + " │")
        print("└" + bar + "┘")


summary = Summary(_shared_accumulator)
