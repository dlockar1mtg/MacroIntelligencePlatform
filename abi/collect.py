"""Inputs for the AI / Technology Bubble Index (docs/ABI_SPEC.md), saved to a snapshot directory.

Sources (all free, no key):
  SEC EDGAR XBRL company facts and frames   revenue, CapEx, inventory, diluted EPS, shares (with accession + filing date)
  Yahoo Finance chart v8                    daily and month-end closes with split events
  SPDR S&P 500 ETF (SPY) daily holdings     official S&P 500 weights today
  Wikipedia                                 Nasdaq-100 members today (and the S&P 500 list as a fallback)
  Yahoo Finance quoteSummary earningsTrend  EPS estimates now and 90 days ago (archived from the first run on)

Every file records where it came from in MANIFEST.json. Nothing here computes the index.
"""
from __future__ import annotations

import gzip
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path

import pandas as pd

CIK = {"MSFT": 789019, "AMZN": 1018724, "GOOGL": 1652044, "META": 1326801, "NVDA": 1045810, "AMD": 2488,
       "AVGO": 1730168, "MU": 723125, "AAPL": 320193, "TSLA": 1318605}
# Earlier filers whose history continues in today's company: Google Inc. (before Alphabet, 2015), and Broadcom
# Limited and Avago Technologies (before Broadcom Inc., 2018). Same business and per-share basis; the successor's
# own filings win wherever both report a period.
PREDECESSORS = {"GOOGL": [1288776], "AVGO": [1649338, 1441634]}
TAGS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueGoodsNet"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
    "inventory": ["InventoryNet"],
    "eps_diluted": ["EarningsPerShareDiluted"],
    "net_income": ["NetIncomeLoss"],
    "shares_diluted": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
}
DEI_SHARES = "EntityCommonStockSharesOutstanding"
DAILY = ["QQQ", "SOXX", "SPY", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "AVGO", "AMD", "MU"]
MAG7 = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]
START = "2002-01-01"
SEC_UA = os.environ.get("SEC_USER_AGENT") or "MacroIntelligencePlatform research github.com/dlockar1mtg/MacroIntelligencePlatform"
WEB_UA = "Mozilla/5.0 (X11; Linux x86_64) MacroIntelligencePlatform/1.0 (personal research)"
SPY_URL = "https://www.ssga.com/us/en/intermediary/etfs/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx"
NDX_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"
SPX_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


class Fetcher:
    def __init__(self, pause: float = 0.25, retries: int = 3):
        self.pause, self.retries, self._last = pause, retries, 0.0
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def get(self, url: str, headers: dict | None = None, timeout: int = 40) -> bytes:
        err = None
        for attempt in range(self.retries):
            gap = self.pause - (time.monotonic() - self._last)
            if gap > 0:
                time.sleep(gap)
            self._last = time.monotonic()
            try:
                req = urllib.request.Request(url, headers={"User-Agent": WEB_UA, "Accept-Encoding": "gzip", **(headers or {})})
                with self.opener.open(req, timeout=timeout) as r:
                    body = r.read()
                    return gzip.decompress(body) if r.headers.get("Content-Encoding") == "gzip" else body
            except urllib.error.HTTPError as exc:
                err = f"HTTP {exc.code}"
                if exc.code in (400, 401, 403, 404):
                    break
                time.sleep(2 * (attempt + 1) * (3 if exc.code == 429 else 1))
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                err = type(exc).__name__
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"{url[:90]}: {err}")

    def sec(self, url: str) -> dict:
        return json.loads(self.get(url, {"User-Agent": SEC_UA, "Accept": "application/json"}))


# ---------------- SEC ----------------
def sec_facts(f: Fetcher) -> pd.DataFrame:
    rows = []
    for ticker, cik, rank in [(t, c, 0) for t, c in CIK.items()] + [(t, c, i + 1) for t, cs in PREDECESSORS.items() for i, c in enumerate(cs)]:
        try:
            doc = f.sec(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")
        except RuntimeError:
            if rank:
                continue                                     # a predecessor is a bonus, never required
            raise
        for metric, tags in TAGS.items():
            for tag in tags:
                for unit, facts in ((doc.get("facts", {}).get("us-gaap", {}).get(tag) or {}).get("units") or {}).items():
                    for x in facts:
                        rows.append({"ticker": ticker, "metric": metric, "tag": tag, "unit": unit, "start": x.get("start"), "end": x["end"],
                                     "val": x["val"], "accn": x.get("accn"), "fy": x.get("fy"), "fp": x.get("fp"), "form": x.get("form"),
                                     "filed": x.get("filed"), "frame": x.get("frame"), "cik": cik, "successor_rank": rank})
        for unit, facts in ((doc.get("facts", {}).get("dei", {}).get(DEI_SHARES) or {}).get("units") or {}).items():
            for x in facts:
                rows.append({"ticker": ticker, "metric": "shares_outstanding", "tag": DEI_SHARES, "unit": unit, "start": None, "end": x["end"],
                         "val": x["val"], "accn": x.get("accn"), "fy": x.get("fy"), "fp": x.get("fp"), "form": x.get("form"),
                         "filed": x.get("filed"), "frame": x.get("frame"), "cik": cik, "successor_rank": rank})
    return pd.DataFrame(rows)


def sec_tickers(f: Fetcher) -> dict[int, list[str]]:
    """Every ticker of each filer (Alphabet and Berkshire have two)."""
    doc = f.sec("https://www.sec.gov/files/company_tickers.json")
    out: dict[int, list[str]] = {}
    for v in doc.values():
        out.setdefault(int(v["cik_str"]), []).append(str(v["ticker"]).upper().replace(".", "-"))
    return out


def sec_share_frames(f: Fetcher, first_year: int = 2012) -> pd.DataFrame:
    """Shares for every filer, one calendar quarter at a time (dei shares outstanding, else weighted diluted shares)."""
    rows, now = [], datetime.now(timezone.utc)
    for year in range(first_year, now.year + 1):
        for q in range(1, 5):
            if (year, q) > (now.year, (now.month - 1) // 3 + 1):
                break
            for kind, url in (("dei", f"https://data.sec.gov/api/xbrl/frames/dei/{DEI_SHARES}/shares/CY{year}Q{q}I.json"),
                              ("wavg", f"https://data.sec.gov/api/xbrl/frames/us-gaap/WeightedAverageNumberOfDilutedSharesOutstanding/shares/CY{year}Q{q}.json")):
                try:
                    doc = f.sec(url)
                except RuntimeError:
                    continue
                for x in doc.get("data", []):
                    rows.append({"frame": f"{year}Q{q}", "kind": kind, "cik": int(x["cik"]), "end": x.get("end"), "val": x["val"], "accn": x.get("accn")})
    return pd.DataFrame(rows)


# ---------------- constituents ----------------
def spy_holdings(f: Fetcher) -> pd.DataFrame:
    raw = f.get(SPY_URL, {"Accept": "*/*"})
    sheet = pd.read_excel(io.BytesIO(raw), header=None)
    head = next(i for i, r in sheet.iterrows() if "Ticker" in [str(v).strip() for v in r.values])
    df = sheet.iloc[head + 1:].copy()
    df.columns = [str(c).strip() for c in sheet.iloc[head].values]
    df = df[df["Ticker"].notna() & df["Weight"].notna()]
    df = df[pd.to_numeric(df["Weight"], errors="coerce").notna()]
    as_of = next((str(v) for r in sheet.iloc[:head].values for v in r if isinstance(v, str) and "As of" in v), None)
    out = pd.DataFrame({"ticker": df["Ticker"].astype(str).str.strip().str.upper().str.replace(".", "-", regex=False),
                        "name": df["Name"].astype(str).str.strip(), "weight_pct": pd.to_numeric(df["Weight"], errors="coerce")})
    out = out[out["ticker"].str.fullmatch(r"[A-Z][A-Z0-9\-]{0,7}") & ~out["ticker"].str.fullmatch(r"\d+[A-Z]?")]
    out.attrs["as_of"] = as_of
    return out


def _wiki_table(f: Fetcher, url: str, need: tuple[str, ...], min_rows: int = 90) -> tuple[pd.DataFrame, str]:
    """The first table with at least `min_rows` rows and a column named like one of `need` (footnote marks ignored)."""
    html = f.get(url, {"Accept": "text/html"}).decode("utf-8", "replace")
    seen = []
    for t in pd.read_html(io.StringIO(html)):
        cols = [str(c[-1] if isinstance(c, tuple) else c).strip() for c in t.columns]
        t.columns = cols
        seen.append(cols[:6])
        hit = next((c for c in cols for n in need if c.lower().startswith(n.lower())), None)
        if hit and len(t) >= min_rows:
            return t, hit
    raise RuntimeError(f"no table with {need} at {url}; tables seen: {seen[:8]}")


def ndx_members(f: Fetcher) -> pd.DataFrame:
    """Nasdaq-100 members today: Nasdaq's own list first, else the Wikipedia components table."""
    errors = []
    try:
        doc = json.loads(f.get("https://api.nasdaq.com/api/quote/list-type/nasdaq100",
                               {"Accept": "application/json, text/plain, */*", "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"}))
        rows = ((doc.get("data") or {}).get("data") or {}).get("rows") or []
        tick = pd.Series([str(r.get("symbol", "")).strip().upper().replace(".", "-") for r in rows])
        tick = tick[tick.str.fullmatch(r"[A-Z][A-Z0-9\-]{0,7}")]
        if 95 <= len(tick) <= 110:
            out = pd.DataFrame({"ticker": tick}).drop_duplicates()
            out.attrs["source"] = "api.nasdaq.com nasdaq100 list"
            return out
        errors.append(f"nasdaq api returned {len(tick)} symbols")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"nasdaq api: {exc}")
    html = f.get(NDX_URL, {"Accept": "text/html"}).decode("utf-8", "replace")
    for t in pd.read_html(io.StringIO(html)):
        if not 95 <= len(t) <= 110:
            continue
        for c in t.columns:
            vals = t[c].astype(str).str.strip().str.upper().str.replace(".", "-", regex=False)
            if vals.str.fullmatch(r"[A-Z]{1,5}(-[A-Z])?").mean() > 0.9:
                out = pd.DataFrame({"ticker": vals[vals.str.fullmatch(r"[A-Z]{1,5}(-[A-Z])?")]}).drop_duplicates()
                out.attrs["source"] = f"Wikipedia Nasdaq-100 components (column {c})"
                return out
    raise RuntimeError("; ".join(errors) + "; no 95-110 row ticker table on Wikipedia")


def spx_members_wiki(f: Fetcher) -> pd.DataFrame:
    t, col = _wiki_table(f, SPX_URL, ("Symbol", "Ticker"), 400)
    tick = t[col].astype(str).str.strip().str.upper().str.replace(".", "-", regex=False)
    return pd.DataFrame({"ticker": tick}).drop_duplicates()


# ---------------- prices ----------------
def yahoo_chart(f: Fetcher, symbol: str, interval: str = "1d", start: str = START) -> pd.DataFrame:
    p1 = int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp())
    p2 = int(time.time())
    q = urllib.parse.urlencode({"interval": interval, "period1": p1, "period2": p2, "events": "div,splits", "includeAdjustedClose": "true"})
    last = None
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        try:
            doc = json.loads(f.get(f"https://{host}/v8/finance/chart/{urllib.parse.quote(symbol)}?{q}", {"Accept": "application/json"}))
            break
        except RuntimeError as exc:
            last = exc
    else:
        raise last
    r = doc["chart"]["result"][0]
    ts = r.get("timestamp") or []
    close = r["indicators"]["quote"][0].get("close") or []
    adj = (r["indicators"].get("adjclose") or [{}])[0].get("adjclose") or close
    df = pd.DataFrame({"date": pd.to_datetime(ts, unit="s", utc=True).tz_convert("America/New_York").date, "close": close, "adjclose": adj})
    df = df.dropna(subset=["close"]).drop_duplicates("date", keep="last")
    splits = [{"date": str(pd.to_datetime(int(k), unit="s", utc=True).tz_convert("America/New_York").date()),
               "ratio": float(v["numerator"]) / float(v["denominator"])} for k, v in ((r.get("events") or {}).get("splits") or {}).items()]
    df.attrs["splits"] = sorted(splits, key=lambda s: s["date"])
    return df


def unadjusted(df: pd.DataFrame) -> pd.Series:
    """Yahoo closes are split-adjusted; multiply back by the splits after each date to get the price as traded."""
    factor = pd.Series(1.0, index=df.index)
    for s in df.attrs.get("splits", []):
        factor[pd.to_datetime(df["date"]) < pd.Timestamp(s["date"])] *= s["ratio"]
    return df["close"] * factor


# ---------------- estimates ----------------
def yahoo_crumb(f: Fetcher) -> str:
    for url in ("https://fc.yahoo.com", "https://finance.yahoo.com/quote/MSFT"):
        try:
            f.get(url, {"Accept": "text/html"})
        except RuntimeError:
            pass
    return f.get("https://query2.finance.yahoo.com/v1/test/getcrumb", {"Accept": "text/plain"}).decode().strip()


def earnings_trend(f: Fetcher, symbol: str, crumb: str) -> list[dict]:
    q = urllib.parse.urlencode({"modules": "earningsTrend", "crumb": crumb})
    doc = json.loads(f.get(f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}?{q}", {"Accept": "application/json"}))
    out = []
    for t in doc["quoteSummary"]["result"][0]["earningsTrend"]["trend"]:
        if t.get("period") not in ("0y", "+1y"):
            continue
        tr = t.get("epsTrend") or {}
        val = lambda k: (tr.get(k) or {}).get("raw")
        out.append({"ticker": symbol, "period": t["period"], "end_date": t.get("endDate"), "current": val("current"),
                    "d7": val("7daysAgo"), "d30": val("30daysAgo"), "d60": val("60daysAgo"), "d90": val("90daysAgo"),
                    "analysts": ((t.get("earningsEstimate") or {}).get("numberOfAnalysts") or {}).get("raw")})
    return out


# ---------------- the snapshot ----------------
def save_snapshot(directory: Path, archive: Path | None = None, f: Fetcher | None = None) -> dict:
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    f = f or Fetcher()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    man = {"taken_at_utc": now.isoformat(), "files": {}, "errors": {}, "sec_user_agent_set": bool(os.environ.get("SEC_USER_AGENT"))}

    def step(name, fn):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - a failed source is recorded, never fatal for the others
            man["errors"][name] = f"{type(exc).__name__}: {str(exc)[:300]}"
            return None

    facts = step("sec_facts", lambda: sec_facts(f))
    if facts is not None:
        facts.to_csv(d / "sec_facts.csv", index=False)
        man["files"]["sec_facts.csv"] = {"rows": len(facts), "source": "https://data.sec.gov/api/xbrl/companyfacts/"}
    spy = step("spy_holdings", lambda: spy_holdings(f))
    if spy is not None:
        spy.to_csv(d / "spy_holdings.csv", index=False)
        man["files"]["spy_holdings.csv"] = {"rows": len(spy), "as_of": spy.attrs.get("as_of"), "source": SPY_URL}
    spx = spy[["ticker"]] if spy is not None and len(spy) > 400 else step("spx_members_wiki", lambda: spx_members_wiki(f))
    ndx = step("ndx_members", lambda: ndx_members(f))
    if ndx is not None:
        ndx.to_csv(d / "ndx_members.csv", index=False)
        man["files"]["ndx_members.csv"] = {"rows": len(ndx), "source": ndx.attrs.get("source", NDX_URL)}
    tick_map = step("sec_tickers", lambda: sec_tickers(f))
    frames = step("sec_share_frames", lambda: sec_share_frames(f))
    if tick_map:
        (d / "sec_tickers.json").write_text(json.dumps({str(k): v for k, v in sorted(tick_map.items())}) + "\n", encoding="utf-8")
        man["files"]["sec_tickers.json"] = {"rows": len(tick_map), "source": "https://www.sec.gov/files/company_tickers.json"}
    if frames is not None and tick_map:
        wanted = {c for c, ts in tick_map.items() if set(ts) & set((spx["ticker"] if spx is not None else []))} | set(CIK.values())
        frames = frames[frames["cik"].isin(wanted)]           # today's S&P 500 filers only (keeps the file small)
        frames["ticker"] = frames["cik"].map(lambda c: tick_map.get(c, [None])[0])
        frames.to_csv(d / "sec_share_frames.csv", index=False)
        man["files"]["sec_share_frames.csv"] = {"rows": len(frames), "source": "https://data.sec.gov/api/xbrl/frames/"}
    # daily closes: the market tickers and every Nasdaq-100 member; month-end closes for every S&P 500 member
    daily, splits, failed = [], {}, []
    for sym in sorted(set(DAILY) | set(ndx["ticker"] if ndx is not None else [])):
        df = step(f"daily:{sym}", lambda s=sym: yahoo_chart(f, s, "1d", "2011-01-01" if s not in DAILY else START))
        if df is None:
            failed.append(sym)
            continue
        df["ticker"], df["close_unadj"] = sym, unadjusted(df)
        splits[sym] = df.attrs["splits"]
        daily.append(df)
    if daily:
        dd = pd.concat(daily)[["ticker", "date", "close", "adjclose", "close_unadj"]]
        dd.to_csv(d / "prices_daily.csv.gz", index=False, compression="gzip")
        man["files"]["prices_daily.csv.gz"] = {"rows": len(dd), "tickers": int(dd["ticker"].nunique()), "failed": failed,
                                               "source": "Yahoo Finance chart v8, daily, split-adjusted close plus the as-traded close"}
    monthly, mfailed = [], []
    for sym in sorted(set(spx["ticker"] if spx is not None else []) | set(MAG7)):
        df = step(f"monthly:{sym}", lambda s=sym: yahoo_chart(f, s, "1mo", "2011-01-01"))
        if df is None:
            mfailed.append(sym)
            continue
        df["ticker"], df["close_unadj"] = sym, unadjusted(df)
        splits.setdefault(sym, df.attrs["splits"])
        monthly.append(df)
    if monthly:
        mm = pd.concat(monthly)[["ticker", "date", "close", "close_unadj"]]
        mm.to_csv(d / "prices_monthly.csv.gz", index=False, compression="gzip")
        man["files"]["prices_monthly.csv.gz"] = {"rows": len(mm), "tickers": int(mm["ticker"].nunique()), "failed": mfailed,
                                                 "source": "Yahoo Finance chart v8, monthly bars (first trading day of each month)"}
    (d / "splits.json").write_text(json.dumps(splits, indent=0, sort_keys=True) + "\n", encoding="utf-8")
    # estimate trend: appended to the archive, one row per ticker, period and collection day
    crumb = step("yahoo_crumb", lambda: yahoo_crumb(f))
    if crumb:
        rows = []
        for sym in ("NVDA", "MSFT"):
            got = step(f"estimates:{sym}", lambda s=sym: earnings_trend(f, s, crumb))
            rows += [{"collected_on": now.date().isoformat(), "collected_at_utc": now.isoformat(), **r} for r in (got or [])]
        if rows:
            new = pd.DataFrame(rows)
            new.to_csv(d / "estimates_today.csv", index=False)
            man["files"]["estimates_today.csv"] = {"rows": len(new), "source": "Yahoo Finance quoteSummary earningsTrend"}
            if archive is not None:
                archive.parent.mkdir(parents=True, exist_ok=True)
                old = pd.read_csv(archive) if archive.exists() else pd.DataFrame()
                both = pd.concat([old, new]).drop_duplicates(["collected_on", "ticker", "period"], keep="last")
                both.to_csv(archive, index=False)
    (d / "MANIFEST.json").write_text(json.dumps(man, indent=1) + "\n", encoding="utf-8")
    return man


if __name__ == "__main__":
    import sys

    out = save_snapshot(Path(sys.argv[1] if len(sys.argv) > 1 else "data/abi"), Path(sys.argv[2]) if len(sys.argv) > 2 else None)
    print(json.dumps({"files": out["files"], "errors": out["errors"]}, indent=1)[:6000])
