# Phase 4: first results (2026-10-09)

The plan is `docs/RECESSION_MODEL_PLAN.md`, registered before these numbers. Inputs are FRED data as of
2026-10-09. The walk-forward predictions run monthly from 1977-01 to 2025-10, the last month whose
12-month outcome is known: 528 months, 72 of them followed by a recession start.

## Published: the yield-curve model, **12% chance a recession begins by September 2027**

- **Reading for September 2026: 12.3%.** The curve (10-year minus 3-month) is now +1.05 points.
- **Why this model:** it passes the registered rule. Its Brier skill is 0.20, above the 0.10 mark. The
  multi-factor model scored only 0.03, so it did not beat it.
- **How the reading came down:** it peaked at 99% in 2023, while the curve was deeply inverted. It was still
  37% in October 2025 and has fallen every month since, to 13% in the walk-forward run for September 2026.

## Scores (walk-forward; each January's fit sees only outcomes already known)

| Model | Brier | Base-rate Brier | Skill | AUC | Months at 30%+ with no start in 12 months |
|---|---|---|---|---|---|
| **Yield curve** | 0.106 | 0.132 | **0.20** | **0.90** | 97 |
| Multi-factor (6 inputs) | 0.128 | 0.132 | 0.03 | 0.86 | 102 |
| RSI v2.0 (from 1982; reported only) | 0.110 | 0.113 | 0.03 | 0.63 | 71 |
| Base rate | 0.134 | 0.134 | 0 | — | — |

**The multi-factor model ranks months nearly as well as the curve (AUC 0.86) but is badly overconfident.**
Its extra inputs mostly add noise to the level of the probability. The ridge penalty (λ = 1, fixed in the
plan) was not tuned, by design.

**The RSI is a weak predictor a year ahead,** which agrees with phase 3: it is a coincident stress gauge, not
a leading indicator.

## Each recession since 1975 (yield-curve model)

| Recession began | Highest in the 12 months before | First month at 30%+ | Lead |
|---|---|---|---|
| Feb 1980 | 99% | Feb 1979 | 12 months |
| Aug 1981 | 100% | Oct 1980 | 10 months |
| Aug 1990 | 64% | Aug 1989 | 12 months |
| Apr 2001 | 85% | Apr 2000 | 12 months |
| Jan 2008 | 84% | Jan 2007 | 12 months |
| Mar 2020 | 79% | Mar 2019 | 12 months |

Every recession was flagged a year ahead. In 2020 that was luck: the curve inverted in 2019, and the
recession came from the pandemic.

## Reliability: **the high readings overstate the risk**

| Predicted band | Months | Mean predicted | Observed |
|---|---|---|---|
| 0–5% | 243 | 1% | 0.4% |
| 5–15% | 83 | 10% | 2% |
| 15–30% | 40 | 21% | 10% |
| 30–50% | 66 | 40% | 23% |
| 50–100% | 96 | 78% | 52% |

- **The model ranks months well but runs hot.** Read a high number as "the signal that came before every
  recession since 1975", not as the literal odds.
- **A reading near 12% sits in a band where the realized rate was about 2–10%.**

## False alarms (30%+ with no recession start in the next 12 months)

- **Early warnings:** some episodes came 13–26 months before a recession: late 1978, early 1989, March 2000,
  2005–06 and the 2018–19 turn. They were too early, but not wrong about what followed.
- **No recession followed:** 1995–96, late 1997 to early 1999, and mid-2020 (just after the pandemic
  recession).
- **2022–2025:** the long inversion produced 39 months of false alarms, the largest miss in the sample. It is
  why the reading is still falling from a high level.

## Limitations
- **Data:** today's revised data and today's NBER chronology, not the vintages available at the time.
- **Sample:** six recession starts in the scored window. Overlapping monthly predictions are not independent,
  so the skill score has wide error bars.
- **No equities:** the free S&P 500 history starts in 1985.
- **Not a forecast of severity or timing within the year:** only whether a start falls in the next 12
  months.

## Ideas for a later version (would need a new registered plan)
- **Recalibration:** recalibrate the curve model (for example Platt scaling on the walk-forward outputs), so
  the high bands match observed rates.
- **More inputs:** add the near-term forward spread and the excess bond premium, both known to add to the
  curve.
- **Real-time data:** use ALFRED real-time vintages, so the replay sees only what was known each month.
- **Correction to the plan text:** it says "seven recessions since 1975". There are six recession starts after January 1975 (the 1973–75 recession began earlier). The limitation shown with the number now says six. Nothing else in the plan changed.
