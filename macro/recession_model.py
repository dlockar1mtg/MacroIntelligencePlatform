"""Phase 4: probability that a recession begins within 12 months (docs/RECESSION_MODEL_PLAN.md).

Walk-forward logistic models refitted each January on the expanding window of months whose outcome was
known (s <= t - 12). Ridge penalty on standardized inputs; pure numpy (IRLS), deterministic.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

MODEL_ID, MODEL_VERSION = "MIHTS_RECESSION_P12", "1.0.0"
HORIZON = 12
EVAL_START = "1975-01"
FIT_START = "1968-06"
LAMBDA = 1.0
ALARM = 0.30
BANDS = ((0, 0.05), (0.05, 0.15), (0.15, 0.30), (0.30, 0.50), (0.50, 1.0001))
FEATURES = ("curve", "credit", "sahm", "claims_6m", "permits_yoy", "philly")
LAG = {"curve": 0, "credit": 0, "sahm": 1, "claims_6m": 0, "permits_yoy": 1, "philly": 0}
MIN_SKILL = 0.10


def features(data: pd.DataFrame) -> pd.DataFrame:
    """Monthly features, each shifted by its release lag (the value usable at month t)."""
    f = pd.DataFrame(index=data.index)
    f["curve"] = data["GS10"] - data["TB3MS"]
    f["credit"] = data["BAA"] - data["GS10"]
    u3 = data["UNRATE"].rolling(3).mean()
    f["sahm"] = u3 - u3.shift(1).rolling(12).min()
    c3 = data["IC4WSA"].rolling(3).mean()
    f["claims_6m"] = 100 * (c3 / c3.shift(6) - 1)
    p3 = data["PERMIT"].rolling(3).mean()
    f["permits_yoy"] = 100 * (p3 / p3.shift(12) - 1)
    f["philly"] = data["GACDFSA066MSFRBPHI"].rolling(3).mean()
    for k, lag in LAG.items():
        f[k] = f[k].shift(lag)
    return f


def target(data: pd.DataFrame) -> pd.DataFrame:
    """y(t)=1 if a recession starts in t+1..t+12; months in recession are excluded (in_recession=True)."""
    published = data["USREC"].dropna()
    last_known = published.index.max() if len(published) else None
    rec = data["USREC"].fillna(0)
    start = (rec == 1) & (rec.shift(1).fillna(0) == 0)
    starts = set(rec.index[start])
    idx = list(rec.index)
    y = []
    for i, m in enumerate(idx):
        window = idx[i + 1:i + 1 + HORIZON]
        known = len(window) == HORIZON and last_known is not None and window[-1] <= last_known
        y.append(float(any(w in starts for w in window)) if known else math.nan)
    return pd.DataFrame({"y": y, "in_recession": rec.values == 1, "start": start.values}, index=rec.index)


def fit_logit(X: np.ndarray, y: np.ndarray, lam: float = LAMBDA, iters: int = 50) -> np.ndarray:
    """Ridge logistic regression by IRLS. X already has an intercept column (not penalized)."""
    w = np.zeros(X.shape[1])
    pen = np.full(X.shape[1], lam)
    pen[0] = 0.0
    for _ in range(iters):
        z = np.clip(X @ w, -30, 30)
        p = 1 / (1 + np.exp(-z))
        g = X.T @ (p - y) + pen * w
        H = (X * (p * (1 - p))[:, None]).T @ X + np.diag(pen)
        step = np.linalg.solve(H + 1e-9 * np.eye(len(w)), g)
        w -= step
        if np.max(np.abs(step)) < 1e-8:
            break
    return w


def _design(F: pd.DataFrame, mu: pd.Series, sd: pd.Series) -> np.ndarray:
    Z = ((F - mu) / sd).to_numpy()
    return np.column_stack([np.ones(len(Z)), Z])


MODELS = {"BASE_RATE": (), "YIELD_CURVE": ("curve",), "MULTI_FACTOR": FEATURES}


def walk_forward(data: pd.DataFrame, rsi_history: pd.DataFrame | None = None) -> pd.DataFrame:
    """Monthly out-of-sample predictions. Models are refitted each January; months in between reuse that fit."""
    feats, tgt = features(data), target(data)
    if rsi_history is not None and len(rsi_history):
        r = rsi_history.set_index(pd.PeriodIndex(rsi_history["month"], freq="M"))["rsi_unsuppressed"].astype(float)
        feats = feats.join(r.rename("rsi"), how="left")
    models = dict(MODELS)
    if "rsi" in feats:
        models["RSI_V2"] = ("rsi",)
    rows = []
    cache: dict[tuple[str, int], tuple] = {}
    for t in tgt.index[tgt.index >= pd.Period(EVAL_START, "M")]:
        if tgt.loc[t, "in_recession"]:
            continue
        row = {"month": str(t), "y": tgt.loc[t, "y"]}
        for name, cols in models.items():
            key = (name, t.year)
            fit_month = pd.Period(f"{t.year}-01", "M")
            if key not in cache:
                cache[key] = _fit(feats, tgt, fit_month, cols)
            row[name] = _apply(cache[key], feats, t, cols)
        rows.append(row)
    return pd.DataFrame(rows)


def _fit(feats, tgt, fit_month, cols):
    if cols == ():
        train = tgt[(tgt.index <= fit_month - HORIZON) & (~tgt["in_recession"]) & tgt["y"].notna() & (tgt.index >= pd.Period(FIT_START, "M"))]
        return ("base", float(train["y"].mean())) if len(train) else None
    df = feats[list(cols)].join(tgt)
    train = df[(df.index <= fit_month - HORIZON) & (~df["in_recession"]) & df["y"].notna() & (df.index >= pd.Period(FIT_START, "M"))].dropna()
    if len(train) < 60 or train["y"].sum() < 2:
        return None
    mu, sd = train[list(cols)].mean(), train[list(cols)].std().replace(0, 1)
    return ("logit", fit_logit(_design(train[list(cols)], mu, sd), train["y"].to_numpy()), mu, sd)


def _apply(fit, feats, t, cols):
    if fit is None:
        return None
    if fit[0] == "base":
        return fit[1]
    _, w, mu, sd = fit
    if t not in feats.index or feats.loc[t, list(cols)].isna().any():
        return None
    x = _design(feats.loc[[t], list(cols)], mu, sd)
    return float(1 / (1 + math.exp(-float(np.clip(x @ w, -30, 30)[0]))))


def _auc(y: np.ndarray, p: np.ndarray) -> float | None:
    pos, neg = p[y == 1], p[y == 0]
    if not len(pos) or not len(neg):
        return None
    ranks = pd.Series(np.concatenate([pos, neg])).rank().to_numpy()
    return float((ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def score(wf: pd.DataFrame, data: pd.DataFrame) -> dict:
    tgt = target(data)
    starts = [str(m) for m in tgt.index[tgt["start"]] if str(m) >= EVAL_START]
    done = wf[wf["y"].notna()]
    out = {}
    for name in [c for c in wf.columns if c not in ("month", "y")]:
        d = done[done[name].notna()]
        if not len(d):
            continue
        y, p = d["y"].to_numpy(), d[name].to_numpy()
        base = d["BASE_RATE"].to_numpy()
        brier, brier_base = float(np.mean((p - y) ** 2)), float(np.mean((base - y) ** 2))
        pc = np.clip(p, 1e-6, 1 - 1e-6)
        rel = []
        for lo, hi in BANDS:
            m = (p >= lo) & (p < hi)
            rel.append({"band": f"{int(lo * 100)}-{min(100, int(round(hi * 100)))}%", "months": int(m.sum()),
                        "mean_predicted": round(float(p[m].mean()), 3) if m.any() else None,
                        "observed": round(float(y[m].mean()), 3) if m.any() else None})
        events = []
        for s in starts:
            ps = pd.Period(s, "M")
            win = wf[(wf["month"] >= str(ps - 12)) & (wf["month"] < s)]
            vals = win[["month", name]].dropna()
            first = next((r.month for r in vals.itertuples() if getattr(r, name) >= ALARM), None)
            events.append({"recession_start": s, "max_in_12_before": round(float(vals[name].max()), 3) if len(vals) else None,
                           "first_at_or_above_30": first, "lead_months": None if first is None else (ps - pd.Period(first, "M")).n})
        fa = d[(d[name] >= ALARM) & (d["y"] == 0)]
        out[name] = {"months": int(len(d)), "first": d["month"].iloc[0], "last": d["month"].iloc[-1], "events_in_sample": int(y.sum()),
                     "brier": round(brier, 4), "brier_base_rate": round(brier_base, 4),
                     "brier_skill": round(1 - brier / brier_base, 3) if brier_base else None,
                     "log_loss": round(float(-np.mean(y * np.log(pc) + (1 - y) * np.log(1 - pc))), 4),
                     "auc": None if _auc(y, p) is None else round(_auc(y, p), 3), "reliability": rel, "recessions": events,
                     "false_alarm_months_at_or_above_30": int(len(fa))}
    return out


def choose(scores: dict) -> tuple[str | None, str]:
    m2, m1 = scores.get("MULTI_FACTOR"), scores.get("YIELD_CURVE")
    if m2 and m1 and (m2["brier_skill"] or -1) >= MIN_SKILL and m2["brier"] < m1["brier"]:
        return "MULTI_FACTOR", "multi-factor model: Brier skill at least 0.10 and better than the yield curve alone"
    if m1 and (m1["brier_skill"] or -1) >= MIN_SKILL:
        return "YIELD_CURVE", "yield-curve model: Brier skill at least 0.10 (the multi-factor model did not beat it)"
    return None, "no model reached a Brier skill of 0.10 against the base rate"


def current(data: pd.DataFrame, name: str) -> dict:
    """Today's probability from the chosen model, fitted on every month whose outcome is known."""
    feats, tgt = features(data), target(data)
    cols = MODELS[name]
    usable = feats[list(cols)].dropna() if cols else feats
    t = usable.index.max()
    fit = _fit(feats, tgt, t, cols)
    p = _apply(fit, feats, t, cols)
    last = {k: (None if pd.isna(feats.loc[t, k]) else round(float(feats.loc[t, k]), 3)) for k in FEATURES if k in feats}
    return {"as_of_month": str(t), "probability_12m": None if p is None else round(p, 3), "inputs": last}


def build(data: pd.DataFrame, rsi_history: pd.DataFrame | None = None) -> dict:
    wf = walk_forward(data, rsi_history)
    scores = score(wf, data)
    pick, why = choose(scores)
    doc = {"model_id": MODEL_ID, "model_version": MODEL_VERSION, "question": "Will an NBER recession begin within the next 12 months?",
           "plan": "docs/RECESSION_MODEL_PLAN.md", "status": "PUBLISHED" if pick else "NOT_PUBLISHED", "chosen_model": pick, "why": why,
           "calibration": scores, "limitations": ["today's revised data and NBER chronology, not real-time vintages",
                                                   "six recession starts since 1975; overlapping monthly predictions are not independent",
                                                   "no equities (the free S&P 500 history starts in 1985)"]}
    if pick:
        doc.update(current(data, pick))
    doc["history"] = [{"month": r["month"], "p": None if pd.isna(r.get(pick or "YIELD_CURVE")) else round(float(r[pick or "YIELD_CURVE"]), 3),
                       "y": None if pd.isna(r["y"]) else int(r["y"])} for _, r in wf.iterrows()]
    return doc
