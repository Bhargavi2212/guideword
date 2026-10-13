"""Laptop spend so far, from budget/ledger.jsonl (spec 0.3).

Run from the repo root:  python scripts/budget_status.py
Every limit comes from settings (GLOBAL_BUDGET_USD) and config/caps.yaml. Without an
opening balance, "remaining" is refused: earlier spend would be missing from the total.
"""

import sys
from collections import defaultdict
from collections.abc import Sequence

from guideword.config import Config, load_config
from guideword.schema.enums import Environment
from guideword.schema.records import SpendEntry
from guideword.settings import Settings

from live_call import Ledger


def _usd(value: float) -> str:
    return f"${value:,.2f}"


def build_report(entries: Sequence[SpendEntry], config: Config, global_budget_usd: float) -> str:
    laptop = [e for e in entries if e.environment == Environment.LAPTOP]
    has_opening = any(e.kind == "opening_balance" for e in laptop)
    by_model: dict[str, float] = defaultdict(float)
    by_phase: dict[str, float] = defaultdict(float)
    by_use: dict[str, float] = defaultdict(float)
    searches = 0
    for e in laptop:
        if e.kind == "model" and e.model:
            by_model[e.model] += e.cost_usd
        if e.kind != "opening_balance":
            by_phase[e.phase] += e.cost_usd
        by_use[e.use] += e.cost_usd
        searches += e.searches or 0
    total = sum(e.cost_usd for e in laptop)
    allowance = config.caps.environment_allowance(Environment.LAPTOP)

    lines = ["Laptop spend (budget/ledger.jsonl)", "", "By model:"]
    lines += [f"  {model}: {_usd(cost)}" for model, cost in sorted(by_model.items())] or ["  none"]
    lines += ["", "By phase:"]
    lines += [f"  phase {phase}: {_usd(cost)}" for phase, cost in sorted(by_phase.items())] or [
        "  none"
    ]
    lines += ["", f"Tavily searches: {searches}", "", "By use:"]
    for use, rule in config.caps.uses.items():
        if rule.environment != Environment.LAPTOP:
            continue
        spent = by_use.get(use, 0.0)
        if has_opening:
            left = rule.allowance_usd - spent
            lines.append(
                f"  {use:<12} spent {_usd(spent)}  remaining {_usd(left)} of "
                f"{_usd(rule.allowance_usd)}"
            )
        else:
            lines.append(f"  {use:<12} spent {_usd(spent)}")
    lines += ["", f"laptop spent:     {_usd(total)}"]
    if has_opening:
        lines.append(f"laptop remaining: {_usd(allowance - total)} of {_usd(allowance)}")
    else:
        lines.append(
            "laptop remaining: refused. Record the opening balance first: "
            "python scripts/live_call.py opening-balance --usd <amount> --use development"
        )
    lines += [
        "",
        f"GLOBAL_BUDGET_USD: {_usd(global_budget_usd)}",
        "Reconcile weekly against the Token Factory dashboard balance "
        "(the hosted spend_ledger is not read here).",
    ]
    return "\n".join(lines)


def main() -> int:
    settings = Settings()
    config = load_config(global_budget_usd=settings.global_budget_usd)
    print(build_report(Ledger().entries(), config, settings.global_budget_usd))
    return 0


if __name__ == "__main__":
    sys.exit(main())
