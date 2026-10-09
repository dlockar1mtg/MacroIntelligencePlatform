"""Market-based ABI factors: breadth, the trailing-P/E premium (v1.0-R factor 5), reconstructed concentration
history (backtest only) and the estimate-trend revision (v1.0-R factor 7)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .collect import TAGS
from .engine import MAG7_HOLDINGS, Fundamentals


def load_daily(path: Path) -> pd.DataFrame:
    d = pd.read_csv(path, parse_dates=["date"])
    return d.sort_values(["ticker", "date"])


def breadth_series(daily: pd.DataFrame, members: list[str], window: int = 200) -> pd.DataFrame:
    """Daily share of members above their 200-trading-day simple moving average (split-adjusted closes)."""
    px = daily[daily["ticker"].isin(members)].pivot(index="date", columns="ticker", values="close").sort_index()
    sma = px.rolling(window, min_periods=window).mean()
    valid = sma.notna() & px.notna()
    above = (px > sma) & valid
    out = pd.DataFrame({"members_counted": valid.sum(axis=1), "above": above.sum(axis=1)})
    out["members_listed"] = len(members)
    out["pct_above"] = 100 * out["above"] / out["members_counted"].where(out["members_counted"] > 0)
    return out.dropna(subset=["pct_above"])


def close_on(daily_t: pd.DataFrame, when: pd.Timestamp, col: str = "close_unadj"):
    """Last close on or before `when` (and no more than 7 days earlier)."""
    s = daily_t[daily_t["date"] <= when]
    if s.empty or (when - s["date"].iloc[-1]).days > 7:
        return None, None
    return float(s[col].iloc[-1]), s["date"].iloc[-1]


def split_factor(splits: list[dict], after: pd.Timestamp, through: pd.Timestamp) -> float:
    f = 1.0
    for s in splits or []:
        d = pd.Timestamp(s["date"])
        if after < d <= through:
            f *= float(s["ratio"])
    return f


def ttm_eps(fund: Fundamentals, ticker: str, as_of: pd.Timestamp, splits: list[dict]) -> dict | None:
    """Trailing-twelve-month diluted EPS on the share basis traded at `as_of`: the last four standalone quarters
    (a fourth quarter is the fiscal year less nine months), each divided by any split after it was filed."""
    eps = fund.flow_quarters(ticker, "eps_diluted", as_of, TAGS["eps_diluted"])
    if len(eps) < 4:
        return None
    last4 = eps.tail(4)
    ends = pd.to_datetime(last4["end"])
    if not 250 <= (ends.iloc[-1] - ends.iloc[0]).days <= 300:
        return None                                              # a missing quarter in the middle
    adj = [float(r.value) / split_factor(splits, pd.Timestamp(r.filed), as_of) for r in last4.itertuples()]
    return {"eps": float(sum(adj)), "quarters": [round(x, 4) for x in adj], "quarter_end": str(ends.iloc[-1].date()),
            "filed": str(pd.Timestamp(last4["filed"].max()).date())}


def pe_history(fund: Fundamentals, daily: pd.DataFrame, splits: dict, ticker: str, months: pd.DatetimeIndex) -> pd.DataFrame:
    dt = daily[daily["ticker"] == ticker]
    rows = []
    for m in months:
        e = ttm_eps(fund, ticker, m, splits.get(ticker, []))
        px, _ = close_on(dt, m)
        pe = None if (e is None or px is None or e["eps"] <= 0) else px / e["eps"]
        rows.append({"month": m, "price": px, "eps": None if e is None else e["eps"], "pe": pe,
                     "quarter_end": None if e is None else e["quarter_end"]})
    return pd.DataFrame(rows)


def pe_premium(hist: pd.DataFrame, m: pd.Timestamp, lookback: int = 120, minimum: int = 60) -> dict:
    """Premium of the trailing P/E at month `m` over its own mean in the previous `lookback` months."""
    cur = hist[hist["month"] == m]
    if cur.empty or pd.isna(cur["pe"].iloc[0]):
        return {"status": "UNDEFINED", "premium_pct": None}
    past = hist[(hist["month"] < m) & (hist["month"] >= m - pd.DateOffset(months=lookback))]["pe"].dropna()
    if len(past) < minimum:
        return {"status": "INSUFFICIENT_HISTORY", "premium_pct": None, "months": int(len(past))}
    pe, base = float(cur["pe"].iloc[0]), float(past.mean())
    return {"status": "OK", "pe": pe, "baseline_pe": base, "baseline_months": int(len(past)), "premium_pct": 100 * (pe / base - 1)}


def factor_pe(pe_hists: dict[str, pd.DataFrame], m: pd.Timestamp) -> dict:
    per = {t: pe_premium(h, m) for t, h in pe_hists.items()}
    ok = [v["premium_pct"] for v in per.values() if v["status"] == "OK"]
    if len(ok) < 2:
        return {"status": "UNDEFINED", "value": None, "companies": per}
    return {"status": "OK", "value": float(np.mean(ok)), "companies": per, "companies_used": len(ok)}


# ---------------- concentration history (reconstructed; backtest only) ----------------
def concentration_history(frames: pd.DataFrame | None, monthly: pd.DataFrame, members: list[str], months: pd.DatetimeIndex,
                          spy: pd.DataFrame, tickers_by_cik: dict | None = None, splits: dict | None = None,
                          availability_lag_days: int = 45) -> tuple[pd.DataFrame, dict]:
    """Magnificent Seven share of the S&P 500, month by month, rebuilt from today's official weights (backtest only).

    Each of today's SPY holdings keeps its official weight today, and is carried back by its own market-cap change:
    weight(t) ~ weight(today) x [price(t) x shares(t)] / [price(today) x shares(today)], with as-traded prices and SEC
    share counts known 45 days after each calendar quarter (price change alone where no share count is available).
    This keeps each company's float and share-class treatment as S&P applies it today. It assumes those stay
    constant and uses today's members throughout (survivorship bias)."""
    w = spy.groupby("ticker")["weight_pct"].sum()
    w = w[w.index.isin(set(members) | set(MAG7_HOLDINGS))]
    mp = monthly.copy()
    mp["month"] = pd.to_datetime(mp["date"]).dt.to_period("M").dt.to_timestamp("M")
    px = mp.pivot_table(index="month", columns="ticker", values="close_unadj", aggfunc="last").sort_index()
    padj = mp.pivot_table(index="month", columns="ticker", values="close", aggfunc="last").sort_index()
    w = w[w.index.isin(px.columns)]
    from .collect import CIK
    cik_of = {"GOOG": CIK["GOOGL"], **CIK}
    if tickers_by_cik is None and frames is not None:
        tickers_by_cik = {int(c): [t] for c, t in frames.dropna(subset=["ticker", "cik"]).groupby("cik")["ticker"].first().items()}
    for cik, ts in (tickers_by_cik or {}).items():
        for t in ts:
            cik_of.setdefault(str(t).replace(".", "-"), int(cik))
    sh = None
    if frames is not None and len(frames):
        fr = frames.dropna(subset=["cik"]).copy()
        fr["cik"] = fr["cik"].astype(int)
        fr = fr.drop_duplicates(["cik", "frame", "kind"], keep="last")
        pref = fr[fr["kind"] == "dei"].set_index(["cik", "frame"])["val"]
        alt = fr[fr["kind"] == "wavg"].set_index(["cik", "frame"])["val"]
        shares = pref.combine_first(alt).reset_index()
        shares["q_end"] = pd.PeriodIndex(shares["frame"], freq="Q").end_time.normalize()
        sh = shares.pivot_table(index="q_end", columns="cik", values="val", aggfunc="last").sort_index()
    now_m = px.index.max()

    def shares_at(t, m):
        """Share count known at month m, restated to the share basis traded at m (splits after the count)."""
        cik = cik_of.get(t)
        if sh is None or cik not in sh.columns:
            return None
        k = sh[cik][sh.index + pd.Timedelta(days=availability_lag_days) <= m].dropna()
        if k.empty:
            return None
        return float(k.iloc[-1]) * split_factor((splits or {}).get(t, []), pd.Timestamp(k.index[-1]), m)

    now_sh = {t: shares_at(t, now_m) for t in w.index}
    rows, price_only = [], set()
    for m in months:
        if m not in px.index:
            continue
        rel = {}
        for t, wt in w.items():
            p0, p1 = px.at[now_m, t], px.at[m, t]
            if pd.isna(p0) or pd.isna(p1) or p0 <= 0:
                continue
            s1, s0 = shares_at(t, m), now_sh.get(t)
            basis = split_factor((splits or {}).get(t, []), m, now_m)          # shares at m restated to today's basis
            if s1 and s0 and 1 / 3 <= (s1 * basis) / s0 <= 3:
                rel[t] = wt * (p1 * s1) / (p0 * s0)
            else:
                a0, a1 = padj.at[now_m, t], padj.at[m, t]
                if pd.isna(a0) or pd.isna(a1) or a0 <= 0:
                    continue
                rel[t] = wt * a1 / a0
                price_only.add(t)
        mag = [t for t in MAG7_HOLDINGS if t in w.index]
        if not all(t in rel for t in mag) or not rel:
            continue
        rows.append({"month": m, "value": 100 * sum(rel[t] for t in mag) / sum(rel.values()), "companies": len(rel)})
    df = pd.DataFrame(rows)
    info = {"status": "OK" if len(df) else "INSUFFICIENT_DATA", "method": "today's official SPY weights carried back by each company's market-cap change",
            "survivorship": "today's S&P 500 members throughout", "companies": int(len(w)),
            "price_change_only": sorted(price_only)[:60], "price_change_only_count": len(price_only)}
    if len(df):
        info["check_against_official"] = {"reconstructed_latest": float(df["value"].iloc[-1]), "reconstructed_month": str(df["month"].iloc[-1].date())[:7],
                                          "official_today": float(spy[spy["ticker"].isin(MAG7_HOLDINGS)]["weight_pct"].sum())}
    return df, info


# ---------------- estimate trend (v1.0-R factor 7) ----------------
def ntm_blend(fy0: float, fy1: float, fy0_end: pd.Timestamp, on: pd.Timestamp) -> float:
    w = min(1.0, max(0.0, (fy0_end - on).days / 365.0))
    return w * fy0 + (1 - w) * fy1


def factor_revisions(archive: pd.DataFrame | None, on: pd.Timestamp, max_age_days: int = 5) -> dict:
    if archive is None or archive.empty:
        return {"status": "INSUFFICIENT_DATA", "value": None, "why": "no estimate collected yet"}
    a = archive.copy()
    a["collected_on"] = pd.to_datetime(a["collected_on"])
    a = a[a["collected_on"] <= on]
    if a.empty:
        return {"status": "INSUFFICIENT_DATA", "value": None}
    day = a["collected_on"].max()
    a = a[a["collected_on"] == day]
    per = {}
    for t, g in a.groupby("ticker"):
        p = {r.period: r for r in g.itertuples()}
        if "0y" not in p or "+1y" not in p:
            continue
        end0 = pd.Timestamp(p["0y"].end_date)
        try:
            now = ntm_blend(float(p["0y"].current), float(p["+1y"].current), end0, day)
            then = ntm_blend(float(p["0y"].d90), float(p["+1y"].d90), end0, day - pd.Timedelta(days=90))
        except (TypeError, ValueError):
            continue
        if not np.isfinite(now) or not np.isfinite(then) or then <= 0:
            continue
        fixed = {p_: 100 * (float(p[p_].current) / float(p[p_].d90) - 1) for p_ in ("0y", "+1y") if p[p_].d90 and float(p[p_].d90) > 0}
        per[t] = {"ntm_now": now, "ntm_90d_ago": then, "revision_pct": 100 * (now / then - 1), "fy0_end": str(end0.date()),
                  "same_fiscal_year_revision_pct": fixed, "analysts": int(p["0y"].analysts) if p["0y"].analysts == p["0y"].analysts else None}
    status = "OK" if len(per) == 2 else "INSUFFICIENT_DATA"
    age = (on - day).days
    return {"status": "STALE" if status == "OK" and age > max_age_days else status,
            "value": float(np.mean([v["revision_pct"] for v in per.values()])) if status == "OK" else None,
            "collected_on": str(day.date()), "companies": per, "source": "Yahoo Finance earningsTrend (research substitute)"}
