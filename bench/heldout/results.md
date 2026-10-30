# Held-out benchmark results

- Freeze: `phase6-freeze-3` at `67bd9f04315c63b67db08894765497580c2a7119`
- Cases run: 3 (k, m, p)

## Headline: Bhargavi's score, the root cause in the top 3

| Configuration | Top 3 | Wilson interval (0.95) | Top 10 | Wilson interval (0.95) | Partials (not counted) |
|---|---|---|---|---|---|
| Guideword | 0 of 3 | 0.00 to 0.56 | 0 of 3 | 0.00 to 0.56 | 1 |
| Baseline A (5A, checklist) | 2 of 3 | 0.21 to 0.94 | 2 of 3 | 0.21 to 0.94 | 1 |
| Baseline B (one prompt) | 3 of 3 | 0.44 to 1.00 | 3 of 3 | 0.44 to 1.00 | 0 |

A Guideword run that stopped at its cap counts as a miss (P6-6). A partial is shown and never counted.

## Paired, per case (top 3)

| Case | Guideword | Baseline A | Baseline B |
|---|---|---|---|
| k | miss | miss | hit |
| m | miss | hit | hit |
| p | miss | hit | hit |

- Guideword against Baseline A (5A, checklist): 0 cases only Guideword found, 2 only the baseline found; exact McNemar p = 0.5000: no difference is claimed.
- Guideword against Baseline B (one prompt): 0 cases only Guideword found, 3 only the baseline found; exact McNemar p = 0.2500: no difference is claimed.
- With n = 3, the exact test needs at least 6 discordant cases, all one way, to reach p < 0.05.

## Automatic score (not the headline)

First matching line: a key component and a key phrase in the same line (P6-9).

| Case | Guideword | Baseline A | Baseline B | Guideword found anywhere |
|---|---|---|---|---|
| k | top10 | top3 | top3 | 9 |
| m | missed | missed | missed | not found |
| p | missed | missed | missed | not found |

## Per case

- k: Guideword stopped at cap: 10 questions open; coverage 254 / 291 checked, 161 unsure; probe recognised: yes; cost $1.45; time 2582 s
- m: Guideword finished; coverage 380 / 390 checked, 234 unsure; probe recognised: yes; cost $1.28; time 1720 s
- p: Guideword stopped at cap: 180 questions open; coverage 302 / 537 checked, 127 unsure; probe recognised: yes; cost $1.47; time 2428 s

Excluded by the probe (P6-5):
- l: probe named the company and site correctly (DPC Enterprises, Festus MO). Judged by Cowork at Bhargavi's request
- n: probe named the company and site correctly (Shell, Moerdijk); its year was wrong. Judged by Cowork at Bhargavi's request

Not run:
- q: not run (stop rule)
- r: not converted: not run
- s: not converted: not run

## Graders

Graders agree on 8 of 9 top-3 calls; Bhargavi's score is the headline.
- k, Baseline A (5A, checklist): Bhargavi miss, second grader hit

## Development cases (D–G)

Shown separately, as recorded, by configuration as stored, and never pooled: [bench/test5/results.md](../../bench/test5/results.md) (development).

Total paid: $4.19
