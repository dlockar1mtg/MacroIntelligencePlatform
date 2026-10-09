# Phase 4: 12-month recession probability (registered 2026-10-09, before any result)

The owner's decision (Devon, 2026-10-09) on the question is: **will a recession begin within the next 12 months?**
That means an NBER peak, the month after which FRED `USREC` turns on, falls in months t+1 … t+12.

## Target and sample
- **y(t) = 1** if a recession starts in t+1 … t+12, otherwise 0.
- **Months inside a recession are excluded,** both from fitting and from scoring, because the "start" question
  has no meaning there.
- **Outcome lag:** an outcome is known 12 months later, plus NBER's dating lag. The walk-forward fits at t use
  only months s ≤ t − 12, and only recession starts already in the data (the replay uses today's dated
  chronology, which is a stated limitation).

## Features (monthly; same release lags as RSI v2.0; all available from 1968)
| Feature | Series | Reading |
|---|---|---|
| Yield curve | GS10 − TB3MS | percentage points |
| Credit spread | BAA − GS10 | percentage points (Moody's Baa yield over the 10-year) |
| Unemployment momentum | UNRATE | Sahm reading (3-month average above its 12-month low) |
| Claims momentum | IC4WSA | % change of the 3-month average over 6 months |
| Housing | PERMIT | 3-month average, % change on a year earlier |
| Manufacturing | GACDFSA066MSFRBPHI | 3-month average |

Equities are left out: the free S&P 500 history used here starts in 1985, and the model needs the 1970s and
1980s recessions. M2 is left out: its relation to recessions changed across decades.

## Models (logistic; fitted each January on the expanding window; ridge penalty λ = 1 on standardized inputs)
- **M0 BASE_RATE:** the share of past months that were followed by a start.
- **M1 YIELD_CURVE:** the yield curve alone. This is the standard benchmark, in the spirit of the New York
  Fed's model.
- **M2 MULTI_FACTOR:** all six features.
- **M3 RSI_V2:** the RSI v2.0 replay as the single input, from 1990 only. It is reported, never chosen,
  because it has too few events.

## Evaluation (walk-forward, monthly predictions from January 1975 to the last month with a known outcome)
- **Scores:** Brier score, log loss, ROC AUC, and the Brier skill score against M0
  (`1 − Brier/Brier_base`).
- **Reliability:** predictions grouped into bands (0–5%, 5–15%, 15–30%, 30–50%, 50–100%), with the observed
  frequency in each.
- **For each recession since 1975:** the highest probability in the 12 months before it began, and the first
  month at or above 30%. False alarms are counted as months at or above 30% not followed by a start within
  12 months.

## What gets published (pass marks, set now)
- **The rule:** publish **M2** if its walk-forward Brier skill is at least **0.10** and it beats M1 on Brier.
  Otherwise publish **M1**, if M1's skill is at least 0.10. Otherwise publish nothing: the status stays
  `NOT_PUBLISHED`, with the results shown.
- **When published:** the number appears with its model, its skill, its reliability table and the events
  table. It is never framed as certain. Seven recessions since 1975 is still a small sample.
- **Limitations:** stated whatever the outcome. These are today's revised data and today's NBER chronology,
  not real-time vintages.

## Not changed
RSI v2.0 itself (`config/rsi_v2.json`) is untouched. The probability is a separate output with its own
version (`MIHTS_RECESSION_P12` 1.0.0).
