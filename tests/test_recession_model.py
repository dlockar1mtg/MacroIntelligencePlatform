"""Phase 4 recession model: target, no look-ahead, walk-forward scoring, publication rule (synthetic data)."""
import numpy as np
import pandas as pd
import pytest

from macro import recession_model as M


def world(n=700, seed=2, signal=True):
    """Monthly data from 1960 with recessions every ~8 years; the curve inverts ahead of each when `signal`."""
    rng = np.random.default_rng(seed)
    idx = pd.period_range("1960-01", periods=n, freq="M")
    rec = np.zeros(n)
    starts = list(range(120, n - 30, 96))
    for s in starts:
        rec[s:s + 10] = 1
    curve = 1.5 + rng.normal(0, 0.4, n)
    if signal:
        for s in starts:
            curve[s - 14:s - 1] = -0.5 + rng.normal(0, 0.2, 13)
    d = pd.DataFrame({"GS10": 5 + curve, "TB3MS": np.full(n, 5.0), "BAA": 7 + rng.normal(0, 0.3, n), "UNRATE": 5 + rng.normal(0, 0.1, n),
                      "IC4WSA": 300000 * (1 + rng.normal(0, 0.02, n)), "PERMIT": 1300 * (1 + rng.normal(0, 0.03, n)),
                      "GACDFSA066MSFRBPHI": rng.normal(5, 8, n), "USREC": rec}, index=idx)
    return d, [idx[s] for s in starts]


def test_target_marks_the_twelve_months_before_each_start_and_drops_recession_months():
    d, starts = world()
    t = M.target(d)
    s = starts[1]
    assert t.loc[s - 1, "y"] == 1 and t.loc[s - 12, "y"] == 1 and t.loc[s - 13, "y"] == 0
    assert bool(t.loc[s, "in_recession"]) and bool(t.loc[s, "start"])
    assert np.isnan(t["y"].iloc[-1])                                   # outcome not known yet


def test_logit_recovers_a_clear_signal():
    rng = np.random.default_rng(0)
    x = rng.normal(0, 1, 4000)
    y = (rng.random(4000) < 1 / (1 + np.exp(-(-1 + 2 * x)))).astype(float)
    w = M.fit_logit(np.column_stack([np.ones(4000), x]), y, lam=0.0)
    assert w[0] == pytest.approx(-1, abs=0.15) and w[1] == pytest.approx(2, abs=0.2)


def test_walk_forward_uses_no_later_data():
    d, _ = world()
    a = M.walk_forward(d)
    later = d.copy()
    cut = pd.Period("1995-06", "M")
    later.loc[later.index > cut, "GS10"] = 99.0
    later.loc[later.index > cut, "USREC"] = 1.0
    b = M.walk_forward(later)
    upto = a[a["month"] <= "1995-06"].reset_index(drop=True)
    pd.testing.assert_frame_equal(upto.drop(columns="y"), b[b["month"] <= "1995-06"].reset_index(drop=True).drop(columns="y"))


def test_a_curve_that_warns_is_published_and_a_silent_world_is_not():
    d, _ = world()
    doc = M.build(d)
    cal = doc["calibration"]
    assert cal["YIELD_CURVE"]["brier_skill"] > 0.10 and cal["YIELD_CURVE"]["auc"] > 0.8
    assert doc["status"] == "PUBLISHED" and doc["chosen_model"] in ("YIELD_CURVE", "MULTI_FACTOR")
    assert 0 <= doc["probability_12m"] <= 1 and doc["calibration"][doc["chosen_model"]]["reliability"]
    quiet, _ = world(signal=False)
    doc = M.build(quiet)
    assert doc["status"] == "NOT_PUBLISHED" and "probability_12m" not in doc
