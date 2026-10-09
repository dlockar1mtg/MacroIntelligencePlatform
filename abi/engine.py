"""AI / Technology Bubble Index: factors, buckets and composite (docs/ABI_SPEC.md, config/abi_v1.json).

Everything is point in time: a fundamental is usable from its filing date, a price from its close. Missing
inputs stay missing (never scored as zero), and every factor carries the figures it was computed from.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FLOW_METRICS = ("revenue", "capex", "net_income", "shares_diluted")
MAG7_HOLDINGS = ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA")


def load_config(path: Path | None = None) -> dict:
    return json.loads(Path(path or ROOT / "config" / "abi_v1.json").read_text(encoding="utf-8"))


# ---------------- buckets, labels, composite ----------------
def _inside(v: float, lo, hi, kind: str) -> bool:
    above = lo is None or (v > lo if kind in ("open_low", "open_low_closed_high") else v >= lo)
    below = hi is None or (v <= hi if kind in ("closed", "open_low_closed_high") else v < hi)
    return above and below


def bucket(value, bands) -> int | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    hits = [b[2] for b in bands if _inside(float(value), b[0], b[1], b[3] if len(b) > 3 else "default")]
    if len(hits) != 1:
        raise ValueError(f"value {value} falls in {len(hits)} bands")
    return hits[0]


def label(abi, cfg: dict) -> tuple[str, str] | tuple[None, None]:
    if abi is None:
        return None, None
    for lo, hi, code, text in cfg["labels"]:
        if (lo == 0 and 0 <= abi <= hi) or lo < abi <= hi:
            return code, text
    raise ValueError(f"abi {abi} outside 0-100")


def composite(scores: dict, weights: dict) -> float | None:
    """sum(weight * score) over every factor in `weights`; None if any factor is missing."""
    if any(scores.get(k) is None for k in weights):
        return None
    return float(sum(weights[k] * scores[k] for k in weights))


# ---------------- SEC quarters, point in time ----------------
def _prep(facts: pd.DataFrame) -> pd.DataFrame:
    f = facts.copy()
    f["end"] = pd.to_datetime(f["end"])
    f["start"] = pd.to_datetime(f["start"], errors="coerce")
    f["filed"] = pd.to_datetime(f["filed"])
    f["days"] = (f["end"] - f["start"]).dt.days
    f["val"] = pd.to_numeric(f["val"], errors="coerce")
    return f.dropna(subset=["val"])


class Fundamentals:
    """Standalone quarterly flows and quarter-end balances for each company, as known on any date."""

    def __init__(self, facts: pd.DataFrame, cfg: dict):
        self.f = _prep(facts)
        self.cfg = cfg
        self._groups = {k: g for k, g in self.f.groupby(["ticker", "metric"])}

    def _known(self, ticker, metric, as_of) -> pd.DataFrame:
        g = self._groups.get((ticker, metric))
        if g is None:
            return pd.DataFrame(columns=self.f.columns)
        return g[g["filed"] <= as_of]

    @staticmethod
    def _latest_per_period(g: pd.DataFrame, tag_order: list[str], keys: list[str]) -> pd.DataFrame:
        if g.empty:
            return g
        g = g.assign(rank=g["tag"].map({t: i for i, t in enumerate(tag_order)}).fillna(99),
                     succ=g["successor_rank"].fillna(0) if "successor_rank" in g else 0)
        g = g.sort_values(["succ", "rank", "filed"], ascending=[True, True, False])   # today's filer, preferred tag, latest filing
        return g.drop_duplicates(keys, keep="first")

    def flow_quarters(self, ticker, metric, as_of, tag_order) -> pd.DataFrame:
        """Standalone fiscal quarters (end, value, filed, accn, how): direct 3-month facts, else YTD differences."""
        return _flow_cached(self, ticker, metric, pd.Timestamp(as_of).normalize(), tuple(tag_order))

    def instants(self, ticker, metric, as_of, tag_order) -> pd.DataFrame:
        g = self._known(ticker, metric, as_of)
        g = self._latest_per_period(g, list(tag_order), ["end"])
        return g.sort_values("end")[["end", "val", "filed", "accn", "tag"]].rename(columns={"val": "value"}).reset_index(drop=True)


_FLOW_CACHE: dict = {}


def _flow_cached(fund: Fundamentals, ticker, metric, as_of, tag_order):
    g = fund._known(ticker, metric, as_of)
    key = (id(fund), ticker, metric, len(g), tag_order)
    if key in _FLOW_CACHE:
        return _FLOW_CACHE[key]
    g = fund._latest_per_period(g[g["start"].notna()], list(tag_order), ["start", "end"])
    out = {}
    for r in g[(g["days"] >= 80) & (g["days"] <= 100)].itertuples():
        out[r.end] = {"end": r.end, "start": r.start, "value": float(r.val), "filed": r.filed, "accn": r.accn, "tag": r.tag, "how": "reported"}
    # Year-to-date figures share the fiscal year's start: each one minus the previous cumulative figure is a quarter.
    for _, grp in g.groupby("start"):
        prev = None
        for r in grp.sort_values("end").itertuples():
            if prev is None:
                prev = (r.end, float(r.val), r.filed) if 80 <= r.days <= 100 else None
                continue
            if not 60 <= (r.end - prev[0]).days <= 120:
                prev = None
                continue
            if r.end not in out:
                out[r.end] = {"end": r.end, "start": prev[0] + pd.Timedelta(days=1), "value": float(r.val) - prev[1],
                              "filed": max(r.filed, prev[2]), "accn": r.accn, "tag": r.tag, "how": f"year-to-date {r.days} days minus the previous"}
            prev = (r.end, float(r.val), max(r.filed, prev[2]))
    res = pd.DataFrame(sorted(out.values(), key=lambda v: v["end"])) if out else pd.DataFrame(columns=["end", "start", "value", "filed", "accn", "tag", "how"])
    _FLOW_CACHE[key] = res
    return res


def yoy(series: pd.DataFrame, end: pd.Timestamp, value_col: str = "value") -> tuple[float | None, dict | None]:
    """Growth of the period ending `end` over the period ending about a year before (within 20 days)."""
    series = series.assign(end=pd.to_datetime(series["end"]))
    cur = series[series["end"] == end]
    if cur.empty:
        return None, None
    target = end - pd.Timedelta(days=365)
    prior = series[(series["end"] - target).abs() <= pd.Timedelta(days=20)]
    if prior.empty:
        return None, None
    a, b = float(cur[value_col].iloc[-1]), float(prior[value_col].iloc[-1])
    if b <= 0:
        return None, None
    return a / b - 1, {"prior_end": str(prior["end"].iloc[-1].date()), "prior_value": b}


# ---------------- factors ----------------
def _tags(cfg_unused, metric):
    from .collect import TAGS
    return TAGS.get(metric, [])


def factor_capex(fund: Fundamentals, cfg: dict, as_of) -> tuple[dict, dict]:
    """Factors 1 and 2 for the hyperscalers."""
    as_of = pd.Timestamp(as_of)
    comps, rows = cfg["factors"]["capex_vs_revenue_growth"]["companies"], []
    for t in comps:
        rev = fund.flow_quarters(t, "revenue", as_of, _tags(cfg, "revenue"))
        cap = fund.flow_quarters(t, "capex", as_of, _tags(cfg, "capex"))
        both = sorted(set(rev["end"]) & set(cap["end"])) if len(rev) and len(cap) else []
        row = {"ticker": t, "quarter_end": None}
        for end in reversed(both):
            rg, rp = yoy(rev, end)
            cg, cp = yoy(cap, end)
            if rg is None or cg is None:
                continue
            r, c = rev[rev["end"] == end].iloc[-1], cap[cap["end"] == end].iloc[-1]
            row = {"ticker": t, "quarter_end": str(end.date()), "revenue": r["value"], "capex": c["value"],
                   "revenue_growth": rg, "capex_growth": cg, "intensity_pct": 100 * c["value"] / r["value"],
                   "filed": str(max(r["filed"], c["filed"]).date()), "accn": [r["accn"], c["accn"]],
                   "how": [r["how"], c["how"]], "age_days": int((as_of - end).days)}
            break
        rows.append(row)
    ok = [r for r in rows if r["quarter_end"]]
    f1 = {"status": "INSUFFICIENT_DATA", "value": None, "companies": rows}
    f2 = {"status": "INSUFFICIENT_DATA", "value": None, "companies": rows}
    if len(ok) == len(comps):
        mr, mc = np.mean([r["revenue_growth"] for r in ok]), np.mean([r["capex_growth"] for r in ok])
        f1 = {"status": "UNDEFINED" if mr <= 0 else "OK", "value": None if mr <= 0 else float(mc / mr),
              "mean_capex_growth": float(mc), "mean_revenue_growth": float(mr), "companies": rows}
        f2 = {"status": "OK", "value": float(np.mean([r["intensity_pct"] for r in ok])), "companies": rows}
    return f1, f2


def factor_inventory(fund: Fundamentals, cfg: dict, as_of) -> dict:
    as_of = pd.Timestamp(as_of)
    comps, rows = cfg["factors"]["semis_inventory_build"]["companies"], []
    for t in comps:
        rev = fund.flow_quarters(t, "revenue", as_of, _tags(cfg, "revenue"))
        inv = fund.instants(t, "inventory", as_of, _tags(cfg, "inventory"))
        row = {"ticker": t, "quarter_end": None}
        for end in sorted(set(rev["end"]) & set(inv["end"]), reverse=True) if len(rev) and len(inv) else []:
            rg, _ = yoy(rev, end)
            ig, _ = yoy(inv, end)
            if rg is None or ig is None:
                continue
            r, i = rev[rev["end"] == end].iloc[-1], inv[inv["end"] == end].iloc[-1]
            row = {"ticker": t, "quarter_end": str(end.date()), "revenue": r["value"], "inventory": i["value"], "revenue_growth": rg,
                   "inventory_growth": ig, "filed": str(max(r["filed"], i["filed"]).date()), "accn": [r["accn"], i["accn"]],
                   "age_days": int((as_of - end).days)}
            break
        rows.append(row)
    ok = [r for r in rows if r["quarter_end"]]
    if len(ok) < len(comps):
        return {"status": "INSUFFICIENT_DATA", "value": None, "companies": rows}
    mi, mr = np.mean([r["inventory_growth"] for r in ok]), np.mean([r["revenue_growth"] for r in ok])
    return {"status": "OK", "value": float(100 * (mi - mr)), "mean_inventory_growth": float(mi), "mean_revenue_growth": float(mr), "companies": rows}


def factor_concentration_official(spy: pd.DataFrame | None, as_of_text: str | None) -> dict:
    if spy is None or spy.empty:
        return {"status": "INSUFFICIENT_DATA", "value": None}
    w = spy[spy["ticker"].isin(MAG7_HOLDINGS)]
    found = sorted(set(w["ticker"]))
    missing = [t for t in ("AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA") if t not in found] + ([] if {"GOOGL", "GOOG"} & set(found) else ["GOOGL"])
    if missing:
        return {"status": "INSUFFICIENT_DATA", "value": None, "missing": missing}
    return {"status": "OK", "value": float(w["weight_pct"].sum()), "source": "SPY daily holdings (official S&P 500 weights)",
            "holdings_as_of": as_of_text, "weights": {r.ticker: float(r.weight_pct) for r in w.itertuples()}, "members": int(len(spy))}


def _bucket_all(values: dict, cfg: dict) -> dict:
    out = {}
    for k, spec in cfg["factors"].items():
        v = values.get(k)
        out[k] = None if v is None else bucket(v, spec["bands"])
    return out


def weights(cfg: dict, drop: tuple[str, ...] = ()) -> dict:
    w = {k: v["weight"] for k, v in cfg["factors"].items() if k not in drop}
    s = sum(w.values())
    return {k: v / s for k, v in w.items()}
