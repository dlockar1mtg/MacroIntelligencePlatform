"""Official monthly inputs for the RSI: FRED series (no key needed) and the S&P 500 index.

Daily and weekly series become monthly averages; monthly series keep their month. Each fetch can be saved to
and replayed from a snapshot directory (data/snapshot/), so development and tests run on identical inputs.
"""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

FRED_SERIES = ("PAYEMS", "IC4WSA", "CCSA", "UNRATE", "T10Y3M", "BAMLH0A0HYM2", "BAA10Y", "GACDFSA066MSFRBPHI",
               "PERMIT", "M2SL", "UMCSENT", "DCOILWTICO", "USREC", "MORTGAGE30US",
               "GS10", "TB3MS", "BAA")      # long monthly history for the recession model (docs/RECESSION_MODEL_PLAN.md)
SP500 = "^GSPC"
START = "1959-01-01"


def fetch_fred(series_id: str) -> pd.Series:
    from pandas_datareader import data as web
    df = web.DataReader(series_id, "fred", START, "2040-12-31")
    return pd.to_numeric(df.iloc[:, 0], errors="coerce").dropna()


def fetch_sp500() -> pd.Series:
    """S&P 500 month-end closes from Yahoo's chart endpoint (index level, not total return)."""
    url = ("https://query2.finance.yahoo.com/v8/finance/chart/%5EGSPC?interval=1mo&period1=-1325635200"
           f"&period2={int(time.time())}&includeAdjustedClose=false")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (MacroIntelligencePlatform research)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    r = payload["chart"]["result"][0]
    stamps, closes = r["timestamp"], r["indicators"]["quote"][0]["close"]
    idx = [datetime.fromtimestamp(t, tz=timezone.utc).date() for t in stamps]
    s = pd.Series(closes, index=pd.to_datetime(idx), dtype="float64").dropna()
    return s[~s.index.duplicated(keep="last")]


def to_monthly(s: pd.Series, how: str = "mean") -> pd.Series:
    s = s.sort_index()
    m = s.resample("ME").last() if how == "last" else s.resample("ME").mean()
    m.index = m.index.to_period("M")
    return m.dropna()


def save_snapshot(directory: Path) -> dict:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {"taken_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "series": {}}
    for sid in FRED_SERIES:
        try:
            s = fetch_fred(sid)
        except Exception as exc:  # noqa: BLE001 - one missing series is reported, never fatal here
            manifest["series"][sid] = {"error": str(exc)[:200]}
            continue
        s.to_frame(sid).to_csv(directory / f"{sid}.csv", index_label="DATE")
        manifest["series"][sid] = {"rows": len(s), "first": str(s.index.min().date()), "last": str(s.index.max().date()),
                                   "source": f"https://fred.stlouisfed.org/series/{sid}"}
    try:
        s = fetch_sp500()
        s.to_frame("GSPC").to_csv(directory / "GSPC.csv", index_label="DATE")
        manifest["series"][SP500] = {"rows": len(s), "first": str(s.index.min().date()), "last": str(s.index.max().date()),
                                     "source": "Yahoo Finance chart API, ^GSPC monthly close"}
    except Exception as exc:  # noqa: BLE001
        manifest["series"][SP500] = {"error": str(exc)[:200]}
    (directory / "MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    return manifest


def load_snapshot(directory: Path) -> pd.DataFrame:
    """Monthly frame: one column per series (index: monthly Period)."""
    directory = Path(directory)
    cols = {}
    for path in sorted(directory.glob("*.csv")):
        sid = "^GSPC" if path.stem == "GSPC" else path.stem
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        s = pd.to_numeric(df.iloc[:, 0], errors="coerce").dropna()
        cols[sid] = to_monthly(s, "last" if sid == "^GSPC" else "mean")
    return pd.DataFrame(cols).sort_index()


def latest_observations(directory: Path) -> dict:
    """Most recent raw observation date per series (for freshness, before monthly averaging)."""
    out = {}
    for path in sorted(Path(directory).glob("*.csv")):
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        s = pd.to_numeric(df.iloc[:, 0], errors="coerce").dropna()
        if len(s):
            out["^GSPC" if path.stem == "GSPC" else path.stem] = {"date": str(s.index.max().date()), "value": float(s.iloc[-1])}
    return out
