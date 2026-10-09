"""How RSI v2.0 behaved around past recessions (descriptive; the index is not fitted to them).

Uses NBER recession months (FRED USREC). The data are today's revised vintages, so this is a revised-data
replay, not a real-time one; each month still uses only observations up to its release lag.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "docs" / "legacy_snapshots.json"
ALARM = 0.2          # the v1 boundary between LATE_CYCLE and DETERIORATION


def recession_starts(data: pd.DataFrame, since: str) -> list[pd.Period]:
    rec = data["USREC"].dropna()
    starts = [m for m in rec.index if rec[m] == 1 and (m - 1 not in rec.index or rec[m - 1] == 0)]
    return [m for m in starts if m >= pd.Period(since, "M")]


def episodes(hist: pd.DataFrame, level: float = ALARM) -> list[tuple[str, str, float]]:
    out, start, peak = [], None, None
    for _, r in hist.iterrows():
        v = r["rsi_unsuppressed"]
        if v is not None and v == v and v >= level:
            start = start or r["month"]
            peak = max(peak or v, v)
            last = r["month"]
        elif start:
            out.append((start, last, peak))
            start, peak = None, None
    if start:
        out.append((start, last, peak))
    return out


def evaluate(hist: pd.DataFrame, data: pd.DataFrame, since: str = "1990-01") -> dict:
    h = hist.set_index("month")
    starts = recession_starts(data, since)
    events = []
    for s in starts:
        window = [str(s - k) for k in range(24, -1, -1)]
        vals = [(m, h.at[m, "rsi_unsuppressed"]) for m in window if m in h.index]
        first = next((m for m, v in vals if v is not None and v == v and v >= ALARM), None)
        at = h.at[str(s), "rsi_unsuppressed"] if str(s) in h.index else None
        twelve = h.at[str(s - 12), "rsi_unsuppressed"] if str(s - 12) in h.index else None
        events.append({"recession_start": str(s), "rsi_12_months_before": None if twelve is None else round(float(twelve), 3),
                       "rsi_at_start": None if at is None else round(float(at), 3),
                       "first_month_at_or_above_0_2_within_24_before": first,
                       "lead_months": None if first is None else (s - pd.Period(first, "M")).n,
                       "max_in_24_before": round(float(max(v for _, v in vals if v == v)), 3) if vals else None})
    eps = episodes(hist[hist["month"] >= since])
    rec_months = set(str(m) for m in data["USREC"].dropna().index[data["USREC"].dropna() == 1])
    false_alarms = []
    for a, b, peak in eps:
        pa = pd.Period(a, "M")
        followed = any(pa <= s <= pa + 12 for s in starts) or a in rec_months
        if not followed:
            false_alarms.append({"from": a, "to": b, "peak": round(float(peak), 3)})
    valid = hist[(hist["month"] >= since) & hist["rsi"].notna()]
    bands = valid["band"].value_counts(normalize=True).round(3).to_dict()
    in_rec = valid[valid["month"].isin(rec_months)]
    return {"since": since, "months": int(len(valid)), "recessions": events, "alarm_level": ALARM,
            "episodes_at_or_above_0_2": [{"from": a, "to": b, "peak": round(float(p), 3)} for a, b, p in eps],
            "false_alarms": false_alarms, "share_of_months_by_band": bands,
            "mean_rsi_in_recession_months": round(float(in_rec["rsi"].mean()), 3) if len(in_rec) else None,
            "mean_rsi_outside_recessions": round(float(valid[~valid["month"].isin(rec_months)]["rsi"].mean()), 3),
            "note": "Revised-data replay with release lags; four recessions since 1990 is far too few to call any threshold calibrated."}


def legacy_comparison(hist: pd.DataFrame) -> list[dict]:
    """The earlier analyst readings beside what v2.0 computes for the same month. Never merged."""
    legacy = json.loads(LEGACY.read_text(encoding="utf-8"))["snapshots"]
    h = hist.set_index("month")
    out = []
    for snap in legacy:
        m = snap["as_of"][:7]
        out.append({**snap, "legacy_unverified": True,
                    "v2_recomputed_for_that_month": None if m not in h.index or h.at[m, "rsi"] is None or h.at[m, "rsi"] != h.at[m, "rsi"]
                    else round(float(h.at[m, "rsi"]), 3)})
    return out
