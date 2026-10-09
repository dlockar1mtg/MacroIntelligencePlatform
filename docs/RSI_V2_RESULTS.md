# RSI v2.0: first results (2026-10-09)

The spec is `docs/RSI_V2_SPEC.md`, frozen before these numbers. They come from the PR run on live FRED and
the S&P 500 index (month to date for October 2026).

## Today: −0.55, expansion (coverage 100%)

| System (weight) | Score | Driving readings |
|---|---|---|
| Labor (30%) | −0.47 | Payrolls +51k a month (3-mo avg, Sep) score **+0.32**; claims 1.24 per 1,000 jobs −1.00; Sahm reading 0.0 −1.00 |
| Financial (25%) | −0.44 | Curve +1.06 pt would score −1, but it **is floored at 0**: it was inverted within the last 24 months. HY spread 3.12 −0.88 |
| Real economy (20%) | −0.82 | Philly Fed 42.2 (3-mo avg) −1.00; permits +1.5% y/y −0.54 |
| Liquidity (10%) | −0.77 | M2 +5.7% y/y |
| Market (10%) | −1.00 | S&P 500 6.0% above its 10-month average |
| Consumer (5%) | **+0.83** | Michigan sentiment 51.7 (August, the latest FRED has) |

- **Overlay:** WTI crude is **+60% on a year earlier**, flagged `SHOCK`. It is shown beside the index, not in it.
- **Weakest signs:** slowing payrolls, very low sentiment, and a curve that only recently stopped being
  inverted. Everything else reads supportive.

## History since 1990 (revised data, release lags; nothing fitted)

| Recession began | RSI 12 months before | First at 0.2+ | Highest in the 24 months before |
|---|---|---|---|
| Aug 1990 | — (the replay starts Jan 1990) | after the start (Sep 1990) | 0.14 |
| Apr 2001 | −0.36 | Jan 2001, **3 months** before | 0.40 |
| Jan 2008 | −0.30 | Jan 2008, **at** the start | 0.38 |
| Mar 2020 | −0.34 | after the start (Apr 2020) | −0.13 |

- **The index is coincident, not leading.** It turned when recessions began, never a year ahead.
  2020 was a shock that no slow-moving indicator foresaw.
- **False alarms** (0.2+ without a recession within 12 months):
  - 2002, the jobless recovery after 2001: peak 0.34.
  - April 2025, the tariff shock: peak 0.26.
- **Share of months:** expansion 78%, late cycle 11%, deterioration 6%, recessionary stress 3%, panic 2%.
  The mean is **+0.46 in recession months** and **−0.34** outside them.
- **Four recessions are far too few to call any threshold calibrated.** This is a stress gauge, not a
  forecast. A 12-month probability needs a separately tested model (phase 4).

## Earlier readings (unverified) beside v2.0 for the same month

| As of | Reported then | v2.0 |
|---|---|---|
| 2026-03-27 | +0.22 | −0.19 |
| 2026-04-14 | −0.18 | −0.42 |
| 2026-05-11 | −0.27 | −0.44 |
| 2026-05-22 | −0.45 | −0.44 |
| 2026-06 (three readings) | −0.40 / −0.45 | −0.61 |
| 2026-07 (five readings) | −0.36 to −0.66 | −0.58 |
| 2026-09 | −0.55 to −0.60 | −0.57 |

- **Where they agree:** v2.0 is close to the earlier readings from late May on, and very close in September.
- **Where they don't:** the March reading (+0.22) does not reproduce under the frozen thresholds. v2.0
  reads −0.19 for that month.
- These are monthly values on today's revised data. The earlier readings were mid-month judgments on the
  data of the day, so they are kept side by side and never merged.

## Limitations
- **Revised data:** the replay uses today's revised data, not the vintages available at the time.
- **Substitutions:** the Philly Fed index stands in for ISM. The S&P 500 is the price index, not total return.
- **History window:** the replay starts in January 1990, which leaves the 1990 recession only seven months
  of lead-up.
- **Sentiment lag:** FRED's Michigan sentiment trails by a month or two.
