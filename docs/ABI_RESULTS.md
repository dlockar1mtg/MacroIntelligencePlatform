# AI / Technology Bubble Index: first results (2026-10-09)

The spec is `docs/ABI_SPEC.md` and `config/abi_v1.json`, registered before any data was fetched. One
correction was made before results: the top bucket of factors 1–5 now opens at its lower edge, so an exact
edge such as a ratio of 4.0 scores 75, as the handoff says. The coverage test caught the overlap. Inputs are
from the pull-request run of 2026-10-09.

## Today: **50 / 100, Elevated** (research version 1.0-R)

| # | Factor | Reading | Risk score | Weight | Points |
|---|---|---|---|---|---|
| 1 | Big Tech CapEx growth ÷ revenue growth | **4.02×**: CapEx +90%, revenue +22% (mean of MSFT, AMZN, GOOGL, META; June 2026 quarter) | 100 | 20% | 20.0 |
| 2 | Big Tech CapEx ÷ revenue | **38.5%** (META 49.5%, MSFT 39.8%, GOOGL 37.5%, AMZN 27.0%) | 100 | 10% | 10.0 |
| 3 | Semis inventory growth − revenue growth | **−87.8 pts**: revenue +155% vs inventory +67% (NVDA, AMD, AVGO, MU) | 0 | 15% | 0 |
| 4 | Magnificent Seven share of the S&P 500 | **34.7%** (official SPY weights, Oct 8) | 75 | 20% | 15.0 |
| 5 | Trailing P/E vs own 10-year average *(substitute)* | **−25%**: NVDA 29 vs 59, MSFT 30 vs 34, AVGO 46 vs 53 | 0 | 15% | 0 |
| 6 | Nasdaq-100 members above their 200-day average | **61.6%** (61 of 99) | 50 | 10% | 5.0 |
| 7 | 90-day EPS revision *(substitute)* | **+18.8%**: NVDA +30.7%, MSFT +7.0% (next-12-month blend) | 0 | 10% | 0 |

- **Where the risk is:** spending. The four hyperscalers are growing CapEx four times as fast as revenue,
  and spend 38 cents of every revenue dollar on it. Concentration (34.7%) sits just under the 35% edge of the top bucket.
- **What holds it down:** earnings. Semiconductor revenue is outrunning inventory, and P/Es are below their
  own 10-year averages because profits rose faster than prices. Estimates are still going up.
- **v1.0 as specified is BLOCKED** (no licensed consensus archive). Its five computable factors carry 50.0 of
  their 75 possible points.
- **Fundamentals verified against the filings:** the June 2024 quarter was rebuilt from SEC facts as known on
  Oct 20, 2024, and matched the reported figures:
  - CapEx: MSFT $13.87B (fiscal Q4, year less nine months), AMZN $17.62B, GOOGL $13.19B, META $8.17B.
  - Revenue: $64.73B, $147.98B, $84.74B and $39.07B.
  - Semiconductors: NVDA revenue $30.04B and inventory $6.675B. AMD, AVGO and MU matched too.
- **Micron's latest quarter is real, not an error.** Its fiscal-2026 10-K (filed Oct 9) gives $133.2B for the
  year less $79.0B for nine months, so the September quarter is $54.2B, +379% on a year earlier. It
  dominates factor 3's mean.

## History (ABI-H6: six factors, rescaled, point in time) — Aug 2015 to Sep 2026, 134 months
- **Distribution:** median 35. Healthy 72 months, Elevated 35, Speculative 16, Very healthy 11. It never
  reached Bubble risk.
- **Yearly means:** 2015 28, 2016 38, 2017 23, 2018 31, 2019 27, 2020 31, 2021 25, 2022 45, 2023 45,
  2024 37, 2025 64, 2026 55.
- **Highest readings:**
  - Feb–Mar 2023 (69–71): hyperscaler revenue stalled while CapEx kept rising, and the chip-inventory glut
    hit its worst point.
  - Oct 2025 (74): the CapEx surge.

## Backtest (registered tests; overlapping monthly samples)
| Target | Spearman with ABI-H6 | 90% block-bootstrap interval |
|---|---|---|
| QQQ next 3 months | +0.06 | −0.08 to +0.17 |
| QQQ next 6 months | +0.12 | −0.12 to +0.25 |
| QQQ next 12 months | **+0.28** | −0.04 to +0.53 |
| QQQ worst fall within 12 months | +0.32 (higher index, *shallower* falls) | +0.03 to +0.57 |
| SOXX next 12 months | +0.51 | +0.18 to +0.64 |

| Index third | Months | QQQ next 12 months | Worst QQQ fall | SOXX next 12 months |
|---|---|---|---|---|
| Low (15–28) | 47 | +15.8% | −21.5% | +18.2% |
| Middle (29–42) | 43 | +23.2% | −14.5% | +36.1% |
| High (42–74) | 44 | +29.0% | −14.9% | +60.9% |

**QQQ falls of 20% or more:**
| Peak | Fall | Index at the peak | Highest in the year before |
|---|---|---|---|
| Aug 2018 | −23% | 33 | 43 |
| Feb 2020 | −29% | 22 | 36 |
| Dec 2021 | −35% | 21 | 35 |
| Feb 2025 | −23% | 68 | 68 |

- **Result: no warning value.** The registered claim rule fails: the 12-month correlation is positive, not
  ≤ −0.20. The page therefore says: *"The backtest found no reliable warning value: read the index as a
  description of conditions, not a warning."*
- **What happened instead:** in this decade, a high reading went with the AI build-out continuing, and
  technology kept rising. Three of the four big falls started from Healthy readings. 2025 is the only one
  that started high.
- **False alarms:** 16 months at 60 or more; 9 of them were followed by no 15% fall within a year.
- **Sample size:** one cycle of a structural boom, about 11 years of overlapping months. That is far too
  little to call the thresholds calibrated in either direction.

## Data and limitations
- **SEC company facts** keep the accession number, form, period and filing date of every value.
  - Standalone quarters are differences of year-to-date figures.
  - Predecessor filers extend the history: Google Inc. before Alphabet; Broadcom Ltd and Avago before
    Broadcom Inc. Today's filer wins where both report a period.
  - The SEC requires a contact in the request header, kept as the repository secret `SEC_USER_AGENT`.
- **Concentration history** carries today's official SPY weights back by each company's market-cap change
  (as-traded price × SEC share count, restated for splits).
  - It matches the official figure today (34.74% vs 34.75%).
  - It uses today's members throughout (survivorship bias). Tesla, for example, counts before it joined in
    December 2020.
  - Some companies (107, including Alphabet) use the price change alone, where share counts were missing
    or implausible.
- **Breadth** uses today's Nasdaq-100 members (survivorship bias). Members with fewer than 200 closes are
  excluded and counted.
- **Factor 5 substitute:** GAAP trailing P/E, with the fourth quarter as the fiscal year less nine months.
  Broadcom's GAAP earnings are depressed by acquisition amortisation; its baseline is its own history, so
  this cancels.
- **Factor 7 substitute:** Yahoo's estimate trend, archived from Oct 9, 2026 (`state/abi_estimates.csv`).
  It has no history, so it is excluded from ABI-H6. The next-12-month blend includes the roll from the
  current fiscal year into the next. The same-year revisions (NVDA +4.2% / +25.2%, MSFT +2.0% / +4.8%)
  are shown alongside.
- **Yahoo data** is unofficial and its terms limit use to personal research. It is used for prices,
  estimates and the Nasdaq list fallback only.

## Ideas for a later version (each needs a new registered spec)
1. **A separate Technology Downturn index** (drawdowns, credit, earnings misses), so speculative
   vulnerability and an active bust are not one number. This is the handoff's first improvement idea.
2. **CapEx vs operating cash flow and depreciation**, instead of revenue growth alone. The growth ratio
   explodes whenever revenue growth slows, as in 2022–23.
3. **Median or revenue-weighted semiconductor factors**, so one company (Micron today) cannot dominate.
4. **A real point-in-time consensus archive**, if a licensed source becomes available. It would unblock
   v1.0.
