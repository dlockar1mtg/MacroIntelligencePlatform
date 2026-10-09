"""System audit fixes, 2026-10-09 (synthetic data)."""
import json

import numpy as np
import pandas as pd
import pytest

import run as RUN
from abi import build as B
from abi import engine as A
from macro import data as D
from macro import recession_model as RM
from macro import rsi as R


def test_curve_floor_covers_the_full_24_months_after_the_last_inversion():
    idx = pd.period_range("2023-01", "2027-12", freq="M")
    s = pd.Series(1.0, index=idx)
    s[pd.Period("2025-08", "M")] = -0.2                       # last inverted month
    data = pd.DataFrame({"T10Y3M": s})
    assert R._post_inversion(data, "T10Y3M", pd.Period("2027-08", "M"), 24)
    assert not R._post_inversion(data, "T10Y3M", pd.Period("2027-09", "M"), 24)


def test_recession_target_is_unknown_past_the_last_published_nber_month():
    idx = pd.period_range("2000-01", "2003-12", freq="M")
    rec = pd.Series(0.0, index=idx)
    rec[pd.Period("2003-01", "M"):] = np.nan                  # NBER indicator not yet published
    t = RM.target(pd.DataFrame({"USREC": rec}))
    assert t.loc[pd.Period("2001-12", "M"), "y"] == 0         # window ends 2002-12, known
    assert np.isnan(t.loc[pd.Period("2002-01", "M"), "y"])     # window reaches 2003-01, unknown


def test_fred_snapshot_keeps_observations_that_fell_off_a_rolling_window(tmp_path, monkeypatch):
    old = pd.Series([3.0, 3.1, 3.2], index=pd.to_datetime(["2020-01-01", "2020-02-01", "2020-03-01"]))
    old.to_frame("X").to_csv(tmp_path / "X.csv", index_label="DATE")
    new = pd.Series([3.3, 3.4], index=pd.to_datetime(["2020-03-01", "2020-04-01"]))
    monkeypatch.setattr(D, "FRED_SERIES", ("X",))
    monkeypatch.setattr(D, "fetch_fred", lambda sid: new)
    monkeypatch.setattr(D, "fetch_sp500", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    m = D.save_snapshot(tmp_path)
    got = pd.read_csv(tmp_path / "X.csv", index_col=0)["X"].tolist()
    assert got == [3.0, 3.1, 3.3, 3.4] and m["series"]["X"]["kept_from_earlier_snapshots"] == 2


def test_a_failed_index_input_marks_the_package_degraded(tmp_path):
    cfg = R.load_config()
    (tmp_path / "MANIFEST.json").write_text(json.dumps({"taken_at_utc": "2026-10-09T13:40:00+00:00",
                                                        "series": {"PAYEMS": {"error": "HTTP 500"}, "MORTGAGE30US": {"error": "x"}, "UNRATE": {"rows": 1}}}))
    q = RUN.data_quality(tmp_path, cfg, {"components": [{"component": "payrolls", "status": "OK"}]})
    assert q["status"] == "DEGRADED" and q["failed_series"] == ["PAYEMS"] and "MORTGAGE30US" in q["other_fetch_errors"]
    (tmp_path / "MANIFEST.json").write_text(json.dumps({"series": {"PAYEMS": {"rows": 10}}}))
    assert RUN.data_quality(tmp_path, cfg, {"components": []})["status"] == "OK"


def test_bubble_inputs_drop_a_live_bar_fetched_before_the_close(tmp_path):
    rows = [{"ticker": "QQQ", "date": d, "close": 1, "adjclose": 1, "close_unadj": 1} for d in ("2026-10-08", "2026-10-09")]
    pd.DataFrame(rows).to_csv(tmp_path / "prices_daily.csv.gz", index=False, compression="gzip")
    (tmp_path / "MANIFEST.json").write_text(json.dumps({"taken_at_utc": "2026-10-09T13:45:00+00:00", "files": {}, "errors": {}}))
    inp = B.Inputs(tmp_path, None, A.load_config())
    assert inp.dropped_partial_day == "2026-10-09" and inp.daily["date"].max() == pd.Timestamp("2026-10-08")
    (tmp_path / "MANIFEST.json").write_text(json.dumps({"taken_at_utc": "2026-10-09T21:30:00+00:00", "files": {}, "errors": {}}))
    assert B.Inputs(tmp_path, None, A.load_config()).daily["date"].max() == pd.Timestamp("2026-10-09")
