"""Numbers as the engineer reads them (spec 3.2; PROJECT.md §5 Step 6.2): orders of magnitude,
never false precision. Only the shown text is rounded; stored numbers never are."""

import math

from guideword.schema.enums import Calculation
from guideword.schema.records import LopaRecord


def _power(value: float) -> int:
    return round(math.log10(value))


def frequency_text(per_year: float) -> str:
    """`about 1 in 10,000 years`, or `about 10 per year` for one a year or more."""
    power = _power(per_year)
    if power >= 0:
        return f"about {10**power:,} per year"
    return f"about 1 in {10**-power:,} years"


def gap_text(record: LopaRecord) -> str:
    """The LOPA gap: how far the mitigated frequency is from tolerable, with both."""
    if not record.complete or record.gap is None or record.mitigated_frequency_per_year is None:
        missing = ", ".join(record.missing_fact_ids) or "the initiating frequency"
        return f"incomplete: {missing} missing"
    power = _power(record.gap)
    times = "within tolerable" if record.gap <= 1 else f"about {10 ** max(power, 0):,}× tolerable"
    return (
        f"{times} — mitigated {frequency_text(record.mitigated_frequency_per_year)}, "
        f"tolerable {frequency_text(record.tolerable_per_year)}"
    )


def _two_significant(value: float) -> str:
    """2 significant figures, written without an exponent or a trailing `.0`."""
    if value == 0:
        return "0"
    digits = 1 - math.floor(math.log10(abs(value)))
    rounded = round(value, digits)
    return f"{rounded:.{max(digits, 0)}f}"


def calc_text(calculation: Calculation, value: float) -> str:
    """A physics_calc number as the card and worksheet show it (Phase 4 spec 4.1): 2 significant
    figures; the stored value is never rounded."""
    if calculation == Calculation.BLOCKED_IN_HEATING:
        return f"at least {_two_significant(value)}× design"
    return f"about {_two_significant(value)} minutes"
