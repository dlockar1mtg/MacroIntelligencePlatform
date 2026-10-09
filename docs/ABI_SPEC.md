# AI / Technology Bubble Index: registered specification (2026-10-09, before any data was fetched)

The machine-readable spec is `config/abi_v1.json`. This page explains it. The source is Devon's handoff,
*UIP AI Bubble Index Implementation Handoff* (Oct 9, 2026).

## What it is, and what it is not
- **What it is:** a 0–100 composite. It describes conditions associated with speculative excess in AI-related
  public companies: overinvestment, inventory build, concentration, valuation stretch, narrow breadth and
  falling estimates.
- **What it is not:** a crash probability, a price forecast or a timing system. The labels (Very healthy …
  Extreme bubble) are heuristic, not calibrated.
- **What it informs:** the Watchtower and the Merchants' Guild, as context. It never places or changes a
  trade.

## Two versions (owner decision, 2026-10-09)
| Version | Factor 5 | Factor 7 | Status |
|---|---|---|---|
| **v1.0 (as specified)** | forward P/E vs its 10-year average | 90-day change in next-12-month consensus EPS | **BLOCKED.** No licensed point-in-time consensus archive is available. Factors 1–4 and 6 are still computed and shown. |
| **v1.0-R (research, published)** | trailing P/E from SEC filings vs its own 10-year average | Yahoo's 90-day estimate trend, archived daily from the first collection | Shown as the current score, always labelled "research version". |

Both versions use the same weights, buckets and the other five factors. A missing factor is never scored as
zero: the composite is withheld (`INCOMPLETE`) instead.

## The seven factors
| # | Factor | Weight | Companies | Data source |
|---|---|---|---|---|
| 1 | CapEx growth ÷ revenue growth | 20% | MSFT, AMZN, GOOGL, META | SEC XBRL company facts |
| 2 | CapEx ÷ revenue | 10% | same | SEC |
| 3 | Inventory growth − revenue growth (pp) | 15% | NVDA, AMD, AVGO, MU | SEC |
| 4 | Magnificent Seven share of the S&P 500 | 20% | AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA | SPY daily holdings (official weights). History is reconstructed from SEC shares × prices. |
| 5 | Valuation premium vs own 10-year history | 15% | NVDA, MSFT, AVGO | v1.0-R: SEC diluted EPS + prices |
| 6 | Nasdaq-100 members above their 200-day average | 10% | current members | daily closes |
| 7 | 90-day EPS estimate revision | 10% | NVDA, MSFT | v1.0-R: Yahoo earnings trend |

Bucket edges are in the config. They cover every value exactly once. Exact edges follow the handoff's
wording: for example, a factor-1 ratio of exactly 4.0 scores 75, and breadth of exactly 80% scores 25.

### How the SEC figures are built
- **Revenue:** a quarterly flow. The fourth quarter is the fiscal year minus the first nine months.
- **CapEx:** reported year-to-date in cash-flow statements. Standalone quarters are differences of
  cumulative figures within one fiscal year.
- **Inventory:** a point-in-time balance, compared with the same quarter-end a year earlier.
- **Provenance:** every value keeps its accession number, form, fiscal period, filing date and XBRL tag.
- **Point in time:** a value is usable only from its filing date.

## Edge cases
- Factor 1 is `UNDEFINED` when mean revenue growth is zero or negative.
- A P/E is undefined for zero or negative EPS. That company drops out; with fewer than two companies left,
  the factor is `UNDEFINED`.
- Stale data carries the last verified score with its age and the status `STALE`. Thresholds: fundamentals
  older than 135 days, market or estimate data older than 5 days.

## History and backtest (registered now, run once)
- **Sampling:** month-ends from January 2013, point in time.
- **Variant used, ABI-H6:** factor 7 has no history, so the backtest uses factors 1–6 with the weights
  rescaled. This variant is never shown as today's score.
- **Factor 4 history:** reconstructed from today's S&P 500 members, so it carries survivorship bias. This is
  labelled wherever it appears.
- **Targets:** QQQ's forward 3-, 6- and 12-month return, QQQ's maximum drawdown over the next 12 months, and
  SOXX's 12-month return.
- **Tests:**
  - Spearman correlation, with a 12-month block-bootstrap 90% interval.
  - Mean target by ABI tercile.
  - The reading before each QQQ drawdown of 20% or more.
  - False alarms: 60+ with no 15% drawdown within a year.
- **Claim rule:** the page may say the index has historically preceded weaker technology returns only if
  both of these hold:
  - the 12-month return correlation is ≤ −0.20 and its interval excludes zero;
  - the high tercile's mean drawdown is deeper than the low tercile's.

  Otherwise it says no reliable warning value was found.

## Legacy readings
The five manual readings from June–July 2026 (57.5, 30.0, 47.5, 45.0, 38.75) are in
`docs/abi_legacy_observations.json`. They are marked unverified, shown apart from the computed series, and
never read as a trend. The 38.75 reading is a golden test: its factor scores must reproduce 38.75 exactly.
