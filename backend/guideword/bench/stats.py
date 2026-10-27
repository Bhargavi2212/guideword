"""Phase 6 statistics, fixed before any run (spec P6-11).

- **Wilson score interval**, 95% (z = 1.959963984540054), no continuity correction: hits out of n
  per configuration, top 3 and top 10.
- **Exact McNemar test**: a two-sided binomial test on the discordant cases (b = the first
  configuration hits and the second misses, c the other way), p = min(1, 2 sum_{i <= min(b,c)}
  C(n, i) / 2^n), n = b + c. With few cases it can't reach p < 0.05: the results say how many
  discordant cases, all one way, it would need (`smallest_one_way_discordant`).

Checked against Cowork's hand-worked values in `bench/example_stats.json`.
"""

import math

Z_95 = 1.959963984540054
ALPHA = 0.05


def wilson_95(x: int, n: int) -> tuple[float, float]:
    if n <= 0 or not 0 <= x <= n:
        raise ValueError(f"a Wilson interval needs 0 <= x <= n and n > 0, got {x} of {n}")
    p = x / n
    z2 = Z_95 * Z_95
    centre = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = (Z_95 / (1 + z2 / n)) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return max(0.0, centre - half), min(1.0, centre + half)


def mcnemar_exact(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    tail: float = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2**n
    return min(1.0, 2 * tail)


def smallest_one_way_discordant(alpha: float = ALPHA) -> int:
    """The fewest discordant cases, all one way, for which the exact test gives p < alpha."""
    n = 1
    while mcnemar_exact(n, 0) >= alpha:
        n += 1
    return n
