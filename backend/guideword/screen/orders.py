"""The plant record in each holistic pass's order (Phase 9 spec 9.3).

A long record read once puts whatever sits in the middle at a disadvantage (Liu et al. 2024),
so the whole-plant pass runs several times and each pass reads the same record with its
top-level object lists in a different order, made by code from the pass number alone: pass 1
as stored, pass 2 every list reversed, pass 3 every list rotated by half, then the cycle
repeats. Nothing inside an object changes and no object is added or dropped, so
`check_plant_sent` holds on every pass.
"""

from collections.abc import Callable, Mapping, Sequence
from typing import Any

Order = Callable[[Sequence[Any]], list[Any]]


def _as_stored(items: Sequence[Any]) -> list[Any]:
    return list(items)


def _reversed(items: Sequence[Any]) -> list[Any]:
    return list(reversed(items))


def _rotated_by_half(items: Sequence[Any]) -> list[Any]:
    half = len(items) // 2
    return [*items[half:], *items[:half]]


ORDERS: tuple[Order, ...] = (_as_stored, _reversed, _rotated_by_half)


def plant_in_order(data: Mapping[str, Any], pass_number: int) -> dict[str, Any]:
    """The screen's plant record (`plant_for_screen`) with every top-level list in the order of
    `pass_number`; pass 1 is the record as given."""
    if pass_number < 1:
        raise ValueError("a holistic pass number starts at 1")
    order = ORDERS[(pass_number - 1) % len(ORDERS)]
    return {k: order(v) if isinstance(v, list) else v for k, v in data.items()}
