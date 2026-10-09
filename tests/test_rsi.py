"""RSI v2.0: weights, scoring, exact arithmetic, no look-ahead, coverage, the contract (synthetic data only)."""
import copy
import json

import numpy as np
import pandas as pd
import pytest

from macro import evaluate as E
from macro import rsi as R
from publication.contract import ContractError, build_contract, validate_contract, validate_package, write_package

CFG = R.load_config()


def frame(n=420, start="1990-01", **over):
    idx = pd.period_range(start, periods=n, freq="M")
    rng = np.random.default_rng(1)
    jobs = 110000 + np.cumsum(np.full(n, 180.0))
    d = pd.DataFrame({
        "PAYEMS": jobs, "IC4WSA": jobs * 1.30, "CCSA": jobs * 11, "UNRATE": np.full(n, 4.0) + rng.normal(0, 0.02, n),
        "T10Y3M": np.full(n, 1.5), "BAMLH0A0HYM2": np.full(n, 3.0), "BAA10Y": np.full(n, 1.8),
        "GACDFSA066MSFRBPHI": np.full(n, 10.0), "PERMIT": 1300 * 1.06 ** (np.arange(n) / 12), "M2SL": 3000 * 1.07 ** (np.arange(n) / 12),
        "^GSPC": 300 * 1.015 ** np.arange(n), "UMCSENT": np.full(n, 90.0), "DCOILWTICO": np.full(n, 60.0), "USREC": np.zeros(n)}, index=idx)
    for k, v in over.items():
        d[k] = v
    return d


def test_weights_and_oil_rules():
    assert sum(s["weight"] for s in CFG["systems"].values()) == pytest.approx(1.0)
    bad = copy.deepcopy(CFG)
    bad["systems"]["liquidity"]["components"]["m2"]["series"] = "DCOILWTICO"
    with pytest.raises(ValueError, match="oil"):
        R.check_config(bad)
    bad = copy.deepcopy(CFG)
    bad["systems"]["labor"]["weight"] = 0.31
    with pytest.raises(ValueError, match="sum"):
        R.check_config(bad)


@pytest.mark.parametrize("value,expected", [(2.0, -1.0), (1.0, -1.0), (0.5, 0.0), (0.0, 1.0), (-1.0, 1.0)])
def test_ramp_across_the_v1_band(value, expected):
    assert R.score(value, 1.0, 0.0) == pytest.approx(expected)          # yield curve: >1pp -1, inverted +1


@pytest.mark.parametrize("cats,expected", [
    ((-0.15, -0.90, -0.30, -0.80, -0.80, 0.20), -0.480),   # handoff: July 17 categories, published as -0.46
    ((-0.35, -1.00, -0.60, -1.00, -0.80, 0.20), -0.645),   # July 24-28
    ((-0.55, -0.90, -0.25, -0.85, -0.75, 0.10), -0.595),   # September
])
def test_the_accepted_weights_reproduce_the_handoff_arithmetic(cats, expected):
    w = [CFG["systems"][k]["weight"] for k in ("labor", "financial", "real_economy", "liquidity", "market", "consumer")]
    assert sum(a * b for a, b in zip(w, cats)) == pytest.approx(expected, abs=1e-9)


def test_an_all_supportive_economy_reads_minus_one_and_contributions_add_up():
    r = R.compute(frame(), "2024-12")
    assert r["rsi"] == pytest.approx(-1.0) and r["band"] == "EXPANSION" and r["coverage"] == pytest.approx(1.0)
    assert sum(c["contribution"] for c in r["components"]) == pytest.approx(r["rsi"], abs=1e-3)
    assert r["overlays"]["inflation_energy_shock"]["in_rsi"] is False


def test_release_lags_and_no_look_ahead():
    d = frame()
    a = R.compute(d, "2010-06")
    later = d.copy()
    later.loc[later.index > pd.Period("2010-06", "M"), :] = later.loc[later.index > pd.Period("2010-06", "M"), :] * 0.5
    assert R.compute(later, "2010-06") == a
    pay = next(c for c in a["components"] if c["component"] == "payrolls")
    assert pay["observation_month"] == "2010-05"                          # payrolls are a month behind


def test_an_inverted_then_positive_curve_is_floored_at_neutral():
    curve = np.full(420, 1.5)
    curve[200:215] = -0.5
    d = frame(T10Y3M=curve)
    m = str(d.index[220])
    c = next(x for x in R.compute(d, m)["components"] if x["component"] == "yield_curve")
    assert c["score"] == 0.0 and c["status"] == "FLOORED_AFTER_INVERSION"
    c = next(x for x in R.compute(d, str(d.index[250]))["components"] if x["component"] == "yield_curve")
    assert c["score"] == -1.0


def test_missing_credit_falls_back_and_missing_systems_cut_coverage():
    hy = np.full(420, np.nan)
    d = frame(BAMLH0A0HYM2=hy)
    c = next(x for x in R.compute(d, "2020-01")["components"] if x["component"] == "credit")
    assert c["series"] == "BAA10Y"
    d = frame()
    for col in ("PAYEMS", "IC4WSA", "UNRATE"):
        d[col] = np.nan
    r = R.compute(d, "2020-01")
    assert r["rsi"] is None and r["headline_status"] == "SUPPRESSED_LOW_COVERAGE" and r["coverage"] == pytest.approx(0.70)


def test_stress_episode_is_seen_and_the_contract_validates(tmp_path):
    n = 420
    claims = frame()["IC4WSA"].to_numpy().copy()
    claims[300:320] *= 1.4
    rec = np.zeros(n)
    rec[306:314] = 1
    curve = np.full(n, 1.5)
    curve[280:300] = -0.3
    d = frame(IC4WSA=claims, USREC=rec, T10Y3M=curve, GACDFSA066MSFRBPHI=np.where((np.arange(n) >= 298) & (np.arange(n) < 320), -15.0, 10.0))
    hist = R.history(d, "1990-01", str(d.index[-1]))
    ev = E.evaluate(hist, d, "1990-01")
    assert ev["recessions"][0]["recession_start"] == str(d.index[306])
    assert ev["recessions"][0]["max_in_24_before"] > ev["mean_rsi_outside_recessions"]
    cur = R.compute(d, str(d.index[-1]))
    history = [{"month": r.month, "rsi": None if pd.isna(r.rsi) else float(r.rsi), "band": r.band, "coverage": r.coverage, "recession": False}
               for r in hist.itertuples()]
    c = build_contract(current=cur, history=history, evaluation=ev, legacy=E.legacy_comparison(hist), freshness={}, cfg=CFG,
                       source_commit="abc", run_id="1", generated_at="2026-10-09T00:00:00+00:00")
    write_package(tmp_path, c)
    assert validate_package(tmp_path)["model_version"] == "2.0.0"
    bad = copy.deepcopy(c)
    bad["current"]["components"][0]["contribution"] += 0.1
    with pytest.raises(ContractError, match="contributions"):
        validate_contract(bad)
    bad = copy.deepcopy(c)
    bad["legacy_snapshots"][0]["legacy_unverified"] = False
    with pytest.raises(ContractError, match="legacy"):
        validate_contract(bad)
    bad = copy.deepcopy(c)
    bad["recession_probability"] = {"status": "PUBLISHED"}
    with pytest.raises(ContractError, match="calibration"):
        validate_contract(bad)
    json.dumps(c)
