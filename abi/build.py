"""Assemble the AI / Technology Bubble Index: today's reading (v1.0 strict and v1.0-R), the monthly history
(ABI-H6, backtest only), the registered evaluation, and the contract section the UIP imports."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import engine as A
from . import market as M

FACTOR_NAMES = {"capex_vs_revenue_growth": "Big Tech CapEx growth vs revenue growth", "capex_intensity": "Big Tech CapEx intensity",
                "semis_inventory_build": "Semiconductor inventory build", "mag7_concentration": "Magnificent Seven concentration",
                "forward_pe_premium": "Valuation premium vs own 10-year history", "nasdaq100_breadth": "Nasdaq-100 breadth",
                "eps_revisions": "Earnings estimate revisions"}
PE_COMPANIES = ("NVDA", "MSFT", "AVGO")


class Inputs:
    def __init__(self, snapshot: Path, archive: Path | None, cfg: dict):
        s = Path(snapshot)
        self.cfg = cfg
        self.manifest = json.loads((s / "MANIFEST.json").read_text()) if (s / "MANIFEST.json").exists() else {}
        read = lambda name, **kw: pd.read_csv(s / name, **kw) if (s / name).exists() else None
        self.facts = read("sec_facts.csv")
        self.fund = A.Fundamentals(self.facts, cfg) if self.facts is not None and len(self.facts) else None
        self.spy = read("spy_holdings.csv")
        self.ndx = read("ndx_members.csv")
        self.frames = read("sec_share_frames.csv")
        self.daily = M.load_daily(s / "prices_daily.csv.gz") if (s / "prices_daily.csv.gz").exists() else None
        self.dropped_partial_day = None
        taken = self.manifest.get("taken_at_utc")
        if self.daily is not None and taken:
            ny = pd.Timestamp(taken).tz_convert("America/New_York")
            if ny.hour * 60 + ny.minute < 16 * 60 + 15:      # fetched before the close: today's bar is a live quote
                day = pd.Timestamp(ny.date())
                self.dropped_partial_day = str(day.date()) if (self.daily["date"] == day).any() else None
                self.daily = self.daily[self.daily["date"] != day]
        self.monthly = read("prices_monthly.csv.gz")
        self.splits = json.loads((s / "splits.json").read_text()) if (s / "splits.json").exists() else {}
        self.tickers_by_cik = {int(k): v for k, v in json.loads((s / "sec_tickers.json").read_text()).items()} if (s / "sec_tickers.json").exists() else None
        self.archive = pd.read_csv(archive) if archive is not None and Path(archive).exists() else read("estimates_today.csv")
        self._breadth = None

    def breadth(self) -> pd.DataFrame | None:
        if self._breadth is None and self.daily is not None and self.ndx is not None:
            self._breadth = M.breadth_series(self.daily, list(self.ndx["ticker"]))
        return self._breadth

    def pe_histories(self, months: pd.DatetimeIndex) -> dict:
        if self.fund is None or self.daily is None:
            return {}
        return {t: M.pe_history(self.fund, self.daily, self.splits, t, months) for t in PE_COMPANIES}


def _scored(name: str, f: dict, cfg: dict) -> dict:
    spec = cfg["factors"][name]
    v = f.get("value") if f.get("status") in ("OK", "STALE") else None
    return {"factor": name, "n": spec["n"], "name": FACTOR_NAMES[name], "weight": spec["weight"], "unit": spec["unit"],
            "value": None if v is None else round(float(v), 4), "score": None if v is None else A.bucket(v, spec["bands"]),
            "status": f.get("status"), "detail": _clean(f)}


def _clean(x):
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if not np.isfinite(x) else round(float(x), 6)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (pd.Timestamp, datetime, date)):
        return str(x)[:10]
    return x


def _stale_fundamentals(f: dict, cfg: dict) -> dict:
    ages = [c.get("age_days") for c in f.get("companies") or [] if c.get("age_days") is not None]
    if f.get("status") == "OK" and ages and max(ages) > cfg["freshness"]["fundamentals_max_age_days"]:
        return {**f, "status": "STALE", "oldest_quarter_age_days": max(ages)}
    return f


def current(inp: Inputs, today: pd.Timestamp | None = None) -> dict:
    cfg = inp.cfg
    today = pd.Timestamp(today or datetime.now(timezone.utc).date())
    fac = {}
    if inp.fund is not None:
        f1, f2 = A.factor_capex(inp.fund, cfg, today)
        fac["capex_vs_revenue_growth"], fac["capex_intensity"] = _stale_fundamentals(f1, cfg), _stale_fundamentals(f2, cfg)
        fac["semis_inventory_build"] = _stale_fundamentals(A.factor_inventory(inp.fund, cfg, today), cfg)
    else:
        why = {"status": "INSUFFICIENT_DATA", "value": None, "why": (inp.manifest.get("errors") or {}).get("sec_facts", "no SEC facts")}
        fac.update(capex_vs_revenue_growth=why, capex_intensity=why, semis_inventory_build=why)
    fac["mag7_concentration"] = A.factor_concentration_official(inp.spy, (inp.manifest.get("files", {}).get("spy_holdings.csv") or {}).get("as_of"))
    held = pd.to_datetime(str(fac["mag7_concentration"].get("holdings_as_of") or "").replace("As of ", ""), format="%d-%b-%Y", errors="coerce")
    if fac["mag7_concentration"].get("status") == "OK" and (pd.isna(held) or (today - held).days > cfg["freshness"]["market_max_age_days"]):
        fac["mag7_concentration"] = {**fac["mag7_concentration"], "status": "STALE", "why": "SPY holdings date missing or older than the market freshness limit"}
    month_ends = pd.date_range("2005-01-31", today, freq="ME")
    pe_now = today
    hists = inp.pe_histories(month_ends.append(pd.DatetimeIndex([pe_now]))) if inp.fund is not None else {}
    fac["forward_pe_premium"] = M.factor_pe(hists, pe_now) if hists else {"status": "INSUFFICIENT_DATA", "value": None}
    fac["forward_pe_premium"]["substitute"] = "trailing_pe_premium (v1.0-R)"
    b = inp.breadth()
    if b is not None and len(b):
        last = b.index.max()
        age = (today - pd.Timestamp(last)).days
        counted = int(b.loc[last, "members_counted"])
        status = "INSUFFICIENT_DATA" if counted < M.BREADTH_MIN_MEMBERS else ("STALE" if age > cfg["freshness"]["market_max_age_days"] else "OK")
        fac["nasdaq100_breadth"] = {"status": status, "value": float(b.loc[last, "pct_above"]),
                                    "date": str(pd.Timestamp(last).date()), "above": int(b.loc[last, "above"]), "members_counted": int(b.loc[last, "members_counted"]),
                                    "members_listed": int(b.loc[last, "members_listed"]), "survivorship": "today's Nasdaq-100 members"}
    else:
        fac["nasdaq100_breadth"] = {"status": "INSUFFICIENT_DATA", "value": None}
    fac["eps_revisions"] = M.factor_revisions(inp.archive, today, cfg["freshness"]["estimates_max_age_days"])
    fac["eps_revisions"]["substitute"] = "yahoo_estimate_trend_90d (v1.0-R)"
    rows = {k: _scored(k, fac[k], cfg) for k in cfg["factors"]}
    scores = {k: r["score"] for k, r in rows.items()}
    w = A.weights(cfg)
    abi_r = A.composite(scores, w)
    missing = [k for k, r in rows.items() if r["score"] is None]
    stale = [k for k, r in rows.items() if r["status"] == "STALE"]
    code, text = A.label(abi_r, cfg)
    contributions = {k: (None if r["score"] is None else round(w[k] * r["score"], 4)) for k, r in rows.items()}
    strict_scores = {**scores, "forward_pe_premium": None, "eps_revisions": None}
    return {
        "as_of_date": str(today.date()),
        "research": {"version": cfg["research_version"], "abi": None if abi_r is None else round(abi_r, 4), "label": code, "label_text": text,
                     "status": "INCOMPLETE" if abi_r is None else ("STALE" if stale else "RESEARCH_UNVERIFIED"),
                     "missing": missing, "stale": stale, "contributions": contributions},
        "strict": {"version": cfg["model_version"], "abi": None, "status": "BLOCKED",
                   "why": "factors 5 and 7 need a licensed point-in-time analyst-consensus archive",
                   "partial_points": round(sum(w[k] * v for k, v in strict_scores.items() if v is not None), 4),
                   "partial_weight": round(sum(w[k] for k, v in strict_scores.items() if v is not None), 4)},
        "factors": [rows[k] for k in cfg["factors"]],
    }


# ---------------- history (ABI-H6) ----------------
def history(inp: Inputs, start: str = "2013-01-31", end: pd.Timestamp | None = None) -> pd.DataFrame:
    cfg = inp.cfg
    end = pd.Timestamp(end or datetime.now(timezone.utc).date())
    months = pd.date_range(start, end, freq="ME")
    w6 = A.weights(cfg, drop=("eps_revisions",))
    conc, conc_info = (M.concentration_history(inp.frames, inp.monthly, list(inp.spy["ticker"]), months, inp.spy, inp.tickers_by_cik, inp.splits)
                       if inp.frames is not None and inp.monthly is not None and inp.spy is not None else (pd.DataFrame(columns=["month", "value"]), {}))
    conc = conc.set_index("month")["value"] if len(conc) else pd.Series(dtype=float)
    pe = inp.pe_histories(pd.date_range("2005-01-31", end, freq="ME"))
    b = inp.breadth()
    rows = []
    for m in months:
        vals = {}
        if inp.fund is not None:
            f1, f2 = A.factor_capex(inp.fund, cfg, m)
            f3 = A.factor_inventory(inp.fund, cfg, m)
            vals.update(capex_vs_revenue_growth=f1.get("value") if f1["status"] == "OK" else None,
                        capex_intensity=f2.get("value") if f2["status"] == "OK" else None,
                        semis_inventory_build=f3.get("value") if f3["status"] == "OK" else None)
        vals["mag7_concentration"] = float(conc[m]) if m in conc.index else None
        if pe:
            f5 = M.factor_pe(pe, m)
            vals["forward_pe_premium"] = f5.get("value")
        if b is not None:
            bb = b[b.index <= m]
            vals["nasdaq100_breadth"] = float(bb["pct_above"].iloc[-1]) if len(bb) and (m - pd.Timestamp(bb.index[-1])).days <= 7 else None
        scores = {k: (None if vals.get(k) is None else A.bucket(vals[k], cfg["factors"][k]["bands"])) for k in w6}
        abi = A.composite(scores, w6)
        rows.append({"month": str(m.date())[:7], **{f"{k}": vals.get(k) for k in w6}, **{f"{k}_score": scores[k] for k in w6},
                     "abi_h6": abi, "label": A.label(abi, cfg)[0] if abi is not None else None})
    out = pd.DataFrame(rows)
    out.attrs["concentration"] = conc_info
    return out


# ---------------- evaluation (registered in config/abi_v1.json) ----------------
def _monthly_close(daily: pd.DataFrame, ticker: str, col: str = "adjclose") -> pd.Series:
    d = daily[daily["ticker"] == ticker].set_index("date")[col].sort_index()
    return d.resample("ME").last()


def forward_targets(daily: pd.DataFrame) -> pd.DataFrame:
    q = _monthly_close(daily, "QQQ")
    s = _monthly_close(daily, "SOXX")
    dq = daily[daily["ticker"] == "QQQ"].set_index("date")["adjclose"].sort_index()
    t = pd.DataFrame(index=q.index)
    for h in (3, 6, 12):
        t[f"qqq_{h}m"] = 100 * (q.shift(-h) / q - 1)
    t["soxx_12m"] = 100 * (s.shift(-12) / s - 1)
    dd = []
    for m in t.index:
        win = dq[(dq.index > m) & (dq.index <= m + pd.DateOffset(months=12))]
        if len(win) < 200 or m + pd.DateOffset(months=12) > dq.index.max():
            dd.append(np.nan)
            continue
        start = float(dq[dq.index <= m].iloc[-1])
        path = np.concatenate([[start], win.values])
        dd.append(100 * float((path / np.maximum.accumulate(path) - 1).min()))
    t["qqq_maxdd_12m"] = dd
    t.index = [str(i.date())[:7] for i in t.index]
    return t


def _spearman(x, y) -> float | None:
    ok = ~(np.isnan(x) | np.isnan(y))
    if ok.sum() < 12:
        return None
    return float(pd.Series(x[ok]).rank().corr(pd.Series(y[ok]).rank()))


def _block_bootstrap(x, y, block=12, reps=2000, seed=7) -> list[float] | None:
    ok = ~(np.isnan(x) | np.isnan(y))
    x, y = x[ok], y[ok]
    n = len(x)
    if n < 2 * block:
        return None
    rng = np.random.default_rng(seed)
    starts = np.arange(n - block + 1)
    vals = []
    for _ in range(reps):
        idx = np.concatenate([np.arange(s, s + block) for s in rng.choice(starts, int(np.ceil(n / block)))])[:n]
        r = _spearman(x[idx], y[idx])
        if r is not None and np.isfinite(r):
            vals.append(r)
    return [round(float(np.percentile(vals, 5)), 3), round(float(np.percentile(vals, 95)), 3)]


def drawdowns(daily: pd.DataFrame, ticker="QQQ", threshold=20.0) -> list[dict]:
    p = daily[daily["ticker"] == ticker].set_index("date")["adjclose"].sort_index()
    out, peak_v, peak_d, trough_v, trough_d, in_dd = [], p.iloc[0], p.index[0], None, None, False
    for d, v in p.items():
        if v >= peak_v:
            if in_dd:
                out.append({"peak": str(peak_d.date()), "trough": str(trough_d.date()), "depth_pct": round(100 * (trough_v / peak_v - 1), 1)})
            peak_v, peak_d, trough_v, trough_d, in_dd = v, d, None, None, False
            continue
        if trough_v is None or v < trough_v:
            trough_v, trough_d = v, d
        if 100 * (1 - v / peak_v) >= threshold:
            in_dd = True
    if in_dd:
        out.append({"peak": str(peak_d.date()), "trough": str(trough_d.date()), "depth_pct": round(100 * (trough_v / peak_v - 1), 1), "ongoing": True})
    return out


def evaluate(hist: pd.DataFrame, daily: pd.DataFrame, cfg: dict) -> dict:
    t = forward_targets(daily)
    h = hist.set_index("month")
    j = h.join(t, how="left")
    x = j["abi_h6"].astype(float).to_numpy()
    res = {"months_with_abi": int(np.isfinite(x).sum()), "first": None, "last": None, "correlations": {}, "terciles": {}}
    have = j[j["abi_h6"].notna()]
    if len(have):
        res["first"], res["last"] = have.index[0], have.index[-1]
    for k in ("qqq_3m", "qqq_6m", "qqq_12m", "qqq_maxdd_12m", "soxx_12m"):
        y = j[k].astype(float).to_numpy()
        res["correlations"][k] = {"spearman": None if _spearman(x, y) is None else round(_spearman(x, y), 3),
                                  "interval_90": _block_bootstrap(x, y), "months": int((np.isfinite(x) & np.isfinite(y)).sum())}
    v = have["abi_h6"]
    if len(v.dropna()) >= 9:
        cuts = v.quantile([1 / 3, 2 / 3]).to_list()
        grp = pd.cut(v, [-np.inf, cuts[0], cuts[1], np.inf], labels=["low", "middle", "high"])
        for g in ("low", "middle", "high"):
            sub = j.loc[grp[grp == g].index]
            res["terciles"][g] = {"months": int(len(sub)), "abi_range": [round(float(sub["abi_h6"].min()), 2), round(float(sub["abi_h6"].max()), 2)],
                                  **{k: (None if sub[k].dropna().empty else round(float(sub[k].dropna().mean()), 2)) for k in ("qqq_12m", "qqq_maxdd_12m", "soxx_12m")}}
    dds = [d for d in drawdowns(daily) if d["peak"] >= "2013-01-01"]
    for d in dds:
        pm = d["peak"][:7]
        window = [m for m in h.index if pd.Period(pm) - 12 <= pd.Period(m) <= pd.Period(pm)]
        vals = h.loc[window, "abi_h6"].dropna()
        d["abi_h6_max_12m_before"] = None if vals.empty else round(float(vals.max()), 2)
        d["abi_h6_at_peak_month"] = None if pm not in h.index or pd.isna(h.loc[pm, "abi_h6"]) else round(float(h.loc[pm, "abi_h6"]), 2)
    res["qqq_drawdowns_20pct"] = dds
    hi = j[(j["abi_h6"] >= 60) & j["qqq_maxdd_12m"].notna()]
    res["months_at_60_plus"] = int((j["abi_h6"] >= 60).sum())
    res["false_alarm_months_60_plus"] = int((hi["qqq_maxdd_12m"] > -15).sum())
    c12, iv = res["correlations"]["qqq_12m"]["spearman"], res["correlations"]["qqq_12m"]["interval_90"]
    deeper = bool(res["terciles"]) and res["terciles"]["high"]["qqq_maxdd_12m"] is not None and res["terciles"]["low"]["qqq_maxdd_12m"] is not None \
        and res["terciles"]["high"]["qqq_maxdd_12m"] < res["terciles"]["low"]["qqq_maxdd_12m"]
    passed = c12 is not None and c12 <= -0.20 and iv is not None and iv[1] < 0 and deeper
    res["warning_value"] = {"passed": passed, "rule": cfg["evaluation"]["warning_value_claim"],
                            "statement": "The index has historically preceded weaker technology returns (2013 onward, ABI-H6)." if passed
                            else "The backtest found no reliable warning value: read the index as a description of conditions, not a warning."}
    return res


# ---------------- contract section ----------------
def section(inp: Inputs, today=None, with_history=True) -> dict:
    cfg = inp.cfg
    cur = current(inp, today)
    out = {"model_id": cfg["model_id"], "model_version": cfg["model_version"], "research_version": cfg["research_version"],
           "spec": "docs/ABI_SPEC.md", "labels": cfg["labels"], "labels_status": cfg["labels_status"],
           "bands": {k: v["bands"] for k, v in cfg["factors"].items()}, "current": cur,
           "legacy_observations": json.loads((A.ROOT / "docs" / "abi_legacy_observations.json").read_text())["observations"],
           "inputs": {k: v for k, v in (inp.manifest.get("files") or {}).items()}, "input_errors": {k: v for k, v in (inp.manifest.get("errors") or {}).items()
                                                                                                    if not k.startswith(("daily:", "monthly:"))},
           "taken_at_utc": inp.manifest.get("taken_at_utc"), "automatic_execution_authorized": False,
           "partial_day_dropped": inp.dropped_partial_day,
           "estimates_archive_since": None if inp.archive is None or inp.archive.empty else str(inp.archive["collected_on"].min())}
    if with_history:
        h = history(inp, end=pd.Timestamp(cur["as_of_date"]))
        out["history"] = _clean(h.replace({np.nan: None}).to_dict("records"))
        out["history_variant"] = cfg["history"]["variant"]
        out["concentration_reconstruction"] = _clean(h.attrs.get("concentration") or {})
        out["evaluation"] = _clean(evaluate(h, inp.daily, cfg)) if inp.daily is not None and h["abi_h6"].notna().any() else {"status": "INSUFFICIENT_DATA"}
    return _clean(out)
