# RSI v2.0 specification (frozen 2026-10-09, before any result)

Source: `docs/HANDOFF_2026-10-09.md`. Owner decisions (Devon, 2026-10-09):
- **Home:** this repository, packaged into the UIP like the ETF and Housing domains.
- **Housing:** no second housing score; the Housing platform's V11 cards and rate outlook are reused.
- **PMI substitute:** the Philly Fed manufacturing index (ISM is licensed and no longer on FRED).
- **Scoring:** continuous ramps across the v1 neutral bands.

The executable form is `config/rsi_v2.json`. Changing any number in it makes a new model version.

## Formula
`RSI = 0.30 L + 0.25 F + 0.20 R + 0.10 M + 0.10 E + 0.05 C`, with every component and system in [-1, +1].
Negative readings mean supportive conditions; positive mean stress.

## Components (each scored −1 at its expansion edge, +1 at its stress edge, a straight line between)

| System (weight) | Component (weight within) | Series | Reading | −1 at | +1 at |
|---|---|---|---|---|---|
| Labor (30%) | Payrolls (40%) | PAYEMS | 3-month average monthly change | +150k | 0 |
| | Claims (35%) | IC4WSA ÷ PAYEMS | initial claims (4-week avg.) per 1,000 jobs | 1.38 (≈220k) | 1.63 (≈260k) |
| | Unemployment (25%) | UNRATE | Sahm reading: 3-month avg. above its 12-month low | 0.1 pt | 0.5 pt |
| Financial (25%) | Yield curve (50%) | T10Y3M | 10-year − 3-month | +1.0 pt | 0 (inverted) |
| | Credit (50%) | BAMLH0A0HYM2 (BAA10Y where absent) | high-yield spread | 3.0 (Baa 1.8) | 5.0 (Baa 2.8) |
| Real economy (20%) | Manufacturing (60%) | GACDFSA066MSFRBPHI | Philly Fed index, 3-month avg. | +6 | −6 |
| | Housing (40%) | PERMIT | permits, 3-month avg. vs a year earlier | +5% | −10% |
| Liquidity (10%) | M2 (100%) | M2SL | year-on-year | 6% | 3% |
| Market (10%) | S&P 500 trend (100%) | ^GSPC | month-end vs 10-month average | +5% | −5% |
| Consumer (5%) | Sentiment (100%) | UMCSENT | level | 70 | 50 |

- **Claims are scaled by payroll jobs**, so the 220k/260k thresholds mean the same thing in 1990 as now.
- **Yield-curve floor:** for 24 months after the last inverted month, the curve score cannot fall below 0.
  A recently un-inverted curve is not low risk.
- **Oil** (WTI, year-on-year) is a displayed `inflation_energy_shock` overlay only. It is flagged above +40% or
  below −40%, and is not in the RSI.

## Timing, coverage, staleness
- **Release lags:** each reading uses only data published by its month. Payrolls, unemployment, permits and M2
  lag one month; the other series lag none.
- **Missing or stale components:** a component is stale when its latest observation is more than its lag + 2
  months old. Its weight is shared across the present components of its system. Coverage is reported, and the
  headline is suppressed below 80%.
- **Bands (v1, provisional, not measured frequencies):** below 0 expansion; 0–0.2 late cycle; 0.2–0.4
  deterioration; 0.4–0.6 recessionary stress; above 0.6 panic.

## Evaluation (descriptive; nothing is fitted)
- **Replay** monthly from 1990 on today's revised data, with the release lags above. This is not a real-time,
  vintage-by-vintage test; ALFRED vintages are a later step.
- **For each NBER recession start since 1990:** the RSI 12 months before, the first month within the prior
  24 at or above 0.2 (lead time), and the maximum in that window.
- **False alarms:** episodes at or above 0.2 not followed by a recession start within 12 months.
- **Share of months in each band,** and the mean RSI inside and outside recessions.
- **Four recessions are too few to call any threshold calibrated.** The report says so, whatever it shows.
- **Legacy analyst readings** (`docs/legacy_snapshots.json`) are shown beside the recomputed value for the
  same month. They are marked unverified and never merged.

## Not published until validated
- **12-month recession probability** (phase 4): a walk-forward model on NBER onsets, scored with Brier and log
  loss against a base rate and a yield-curve benchmark.
- **Asset environment score** (phase 5): needs valuation and forward-return inputs.
- **No automatic trades, allocations or purchase decisions,** ever.
