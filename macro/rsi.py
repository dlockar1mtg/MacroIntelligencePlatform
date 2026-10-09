"""Composite Recession Stress Index v2.0 (config/rsi_v2.json, frozen 2026-10-09).

Deterministic: every component is a documented transform of an official monthly series, scored on a straight
ramp across the v1 neutral band, combined with the accepted six-system weights. Each reading uses only data
that would have been published by its as-of month (per-series release lags).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "rsi_v2.json"


def load_config(path: Path = CONFIG) -> dict:
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    check_config(cfg)
    return cfg


def check_config(cfg: dict) -> None:
    total = sum(s["weight"] for s in cfg["systems"].values())
    if abs(total - 1) > 1e-9:
        raise ValueError(f"system weights sum to {total}, not 1")
    for name, s in cfg["systems"].items():
        inner = sum(c["weight"] for c in s["components"].values())
        if abs(inner - 1) > 1e-9:
            raise ValueError(f"{name} component weights sum to {inner}, not 1")
        for cname, c in s["components"].items():
            if c["expansion"] == c["stress"]:
                raise ValueError(f"{cname}: expansion and stress anchors are equal")
    if any("DCOILWTICO" == c["series"] for s in cfg["systems"].values() for c in s["components"].values()):
        raise ValueError("oil is an overlay in v2.0, not an RSI input")


def score(value: float, expansion: float, stress: float) -> float:
    """-1 at (and beyond) the expansion edge, +1 at (and beyond) the stress edge, straight line between."""
    t = (value - expansion) / (stress - expansion)
    return max(-1.0, min(1.0, -1.0 + 2.0 * t))


def band(rsi: float, cfg: dict) -> str:
    for b in cfg["bands"]:
        if rsi < b["below"]:
            return b["label"]
    return cfg["bands"][-1]["label"]


def _upto(series: pd.Series, month: pd.Period) -> pd.Series:
    s = series.dropna()
    return s[s.index <= month]


def transform(name: str, s: pd.Series, month: pd.Period, data: pd.DataFrame) -> tuple[float, str] | None:
    """(value, observation month) for a transform, using observations through `month` only."""
    s = _upto(s, month)
    if s.empty:
        return None
    last = s.index[-1]
    if name == "level":
        return float(s.iloc[-1]), str(last)
    if name == "avg_3m":
        w = s[s.index > last - 3]
        return (float(w.mean()), str(last)) if len(w) == 3 else None
    if name == "diff_3m_avg":
        if last - 3 not in s.index:
            return None
        return float((s.loc[last] - s.loc[last - 3]) / 3), str(last)
    if name == "yoy":
        if last - 12 not in s.index or not s.loc[last - 12]:
            return None
        return float(100 * (s.loc[last] / s.loc[last - 12] - 1)), str(last)
    if name == "yoy_3m_avg":
        now = s[s.index > last - 3]
        then = s[(s.index > last - 15) & (s.index <= last - 12)]
        if len(now) != 3 or len(then) != 3 or not then.mean():
            return None
        return float(100 * (now.mean() / then.mean() - 1)), str(last)
    if name == "sahm":
        avg = s.rolling(3).mean().dropna()
        if len(avg) < 13:
            return None
        return float(avg.iloc[-1] - avg.iloc[-13:-1].min()), str(avg.index[-1])
    if name == "vs_10m_avg":
        w = s[s.index > last - 10]
        if len(w) != 10:
            return None
        return float(100 * (s.iloc[-1] / w.mean() - 1)), str(last)
    if name == "per_thousand_payroll_jobs":
        jobs = _upto(data["PAYEMS"], month) if "PAYEMS" in data else pd.Series(dtype=float)
        if jobs.empty:
            return None
        return float(s.iloc[-1] / jobs.iloc[-1]), str(last)       # claims (count) / payrolls (thousands) = per 1,000 jobs
    raise ValueError(f"unknown transform {name}")


def _post_inversion(data: pd.DataFrame, series: str, month: pd.Period, months: int) -> bool:
    s = _upto(data[series], month) if series in data else pd.Series(dtype=float)
    recent = s[s.index >= month - months]           # the last inverted month plus the next `months` months
    return bool((recent < 0).any())


def compute(data: pd.DataFrame, as_of: str | pd.Period, cfg: dict | None = None) -> dict:
    """The RSI as it would have read at the end of `as_of`, from data published by then."""
    cfg = cfg or load_config()
    month = pd.Period(as_of, "M")
    extra = cfg["coverage"]["stale_after_extra_months"]
    systems, comps = {}, []
    total_w = coverage = 0.0
    rsi_acc = 0.0
    for sname, sys_cfg in cfg["systems"].items():
        acc = w_present = 0.0
        for cname, c in sys_cfg["components"].items():
            visible = month - c["lag_months"]
            used = c["series"]
            anchors = (c["expansion"], c["stress"])
            got = transform(c["transform"], data[used], visible, data) if used in data else None
            fb = c.get("fallback")
            if fb and (got is None or pd.Period(got[1], "M") < visible - extra) and fb["series"] in data:
                alt = transform(c["transform"], data[fb["series"]], visible, data)
                if alt is not None:
                    used, anchors, got = fb["series"], (fb["expansion"], fb["stress"]), alt
            row = {"system": sname, "component": cname, "series": used, "unit": c["unit"], "within_weight": c["weight"],
                   "system_weight": sys_cfg["weight"], "value": None, "score": None, "observation_month": None,
                   "status": "MISSING", "contribution": 0.0}
            if got is not None:
                value, obs = got
                stale = pd.Period(obs, "M") < visible - extra
                sc = score(value, *anchors)
                floor = c.get("post_inversion_floor")
                floored = False
                if floor and sc < floor["floor"] and _post_inversion(data, c["series"], visible, floor["months"]):
                    sc, floored = floor["floor"], True
                row.update(value=round(value, 4), score=round(sc, 4), observation_month=obs,
                           status="STALE" if stale else ("FLOORED_AFTER_INVERSION" if floored else "OK"),
                           anchors={"expansion": anchors[0], "stress": anchors[1]})
                if not stale:
                    acc += c["weight"] * sc
                    w_present += c["weight"]
            comps.append(row)
        if w_present > 0:
            s_score = acc / w_present
            systems[sname] = {"weight": sys_cfg["weight"], "score": round(s_score, 4), "coverage": round(w_present, 4)}
            rsi_acc += sys_cfg["weight"] * s_score
            total_w += sys_cfg["weight"]
            coverage += sys_cfg["weight"] * w_present
        else:
            systems[sname] = {"weight": sys_cfg["weight"], "score": None, "coverage": 0.0}
    rsi = rsi_acc / total_w if total_w else math.nan
    for r in comps:
        s = systems[r["system"]]
        if r["status"] in ("OK", "FLOORED_AFTER_INVERSION") and s["score"] is not None:
            r["contribution"] = round(r["system_weight"] / total_w * r["within_weight"] / s["coverage"] * r["score"], 4)
    ok = coverage >= cfg["coverage"]["minimum"] and rsi == rsi
    overlay = {}
    for oname, o in cfg.get("overlays", {}).items():
        got = transform(o["transform"], data[o["series"]], month, data) if o["series"] in data else None
        if got:
            v = got[0]
            overlay[oname] = {"value": round(v, 2), "observation_month": got[1], "unit": o["unit"], "in_rsi": False,
                              "flag": "SHOCK" if v > o["shock_above"] else "SLUMP" if v < o["slump_below"] else "NONE"}
    return {"as_of_month": str(month), "model_version": cfg["model_version"], "rsi": round(rsi, 4) if ok else None,
            "rsi_unsuppressed": round(rsi, 4) if rsi == rsi else None, "band": band(rsi, cfg) if ok else None,
            "coverage": round(coverage, 4), "headline_status": "PUBLISHED" if ok else "SUPPRESSED_LOW_COVERAGE",
            "systems": systems, "components": comps, "overlays": overlay}


def history(data: pd.DataFrame, start: str, end: str, cfg: dict | None = None) -> pd.DataFrame:
    cfg = cfg or load_config()
    rows = []
    for m in pd.period_range(start, end, freq="M"):
        r = compute(data, m, cfg)
        rows.append({"month": str(m), "rsi": r["rsi"], "rsi_unsuppressed": r["rsi_unsuppressed"], "band": r["band"],
                     "coverage": r["coverage"], **{f"sys_{k}": v["score"] for k, v in r["systems"].items()}})
    return pd.DataFrame(rows)
