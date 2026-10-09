"""AI / Technology Bubble Index: buckets, labels, composite, quarterization and point in time (synthetic data)."""
import json
import math

import pandas as pd
import pytest

from abi import engine as A

CFG = A.load_config()


def test_weights_sum_to_one_and_every_value_lands_in_exactly_one_band():
    assert sum(f["weight"] for f in CFG["factors"].values()) == pytest.approx(1.0)
    for name, spec in CFG["factors"].items():
        edges = sorted({e for b in spec["bands"] for e in b[:2] if e is not None})
        probes = [edges[0] - 1e6] + [x for e in edges for x in (e - 1e-9, e, e + 1e-9)] + [edges[-1] + 1e6]
        for v in probes:
            assert A.bucket(v, spec["bands"]) in (0, 25, 50, 75, 100), (name, v)


@pytest.mark.parametrize("factor,value,score", [
    ("capex_vs_revenue_growth", 1.4999, 0), ("capex_vs_revenue_growth", 1.5, 25), ("capex_vs_revenue_growth", 2.0, 50),
    ("capex_vs_revenue_growth", 3.0, 75), ("capex_vs_revenue_growth", 4.0, 75), ("capex_vs_revenue_growth", 4.0001, 100),
    ("capex_intensity", 9.99, 0), ("capex_intensity", 10, 25), ("capex_intensity", 25, 75), ("capex_intensity", 25.01, 100),
    ("semis_inventory_build", -0.1, 0), ("semis_inventory_build", 0, 25), ("semis_inventory_build", 20, 75), ("semis_inventory_build", 20.1, 100),
    ("mag7_concentration", 19.9, 0), ("mag7_concentration", 30, 75), ("mag7_concentration", 35, 75), ("mag7_concentration", 35.5, 100),
    ("forward_pe_premium", -1, 0), ("forward_pe_premium", 0, 25), ("forward_pe_premium", 60, 75), ("forward_pe_premium", 61, 100),
    ("nasdaq100_breadth", 80.1, 0), ("nasdaq100_breadth", 80, 25), ("nasdaq100_breadth", 70, 50), ("nasdaq100_breadth", 60, 75),
    ("nasdaq100_breadth", 50, 75), ("nasdaq100_breadth", 49.9, 100),
    ("eps_revisions", 10.1, 0), ("eps_revisions", 10, 25), ("eps_revisions", 5, 50), ("eps_revisions", 0, 75),
    ("eps_revisions", -5, 75), ("eps_revisions", -5.1, 100),
])
def test_exact_edges_follow_the_handoff_wording(factor, value, score):
    assert A.bucket(value, CFG["factors"][factor]["bands"]) == score


def test_the_july_16_reading_reproduces_38_75():
    legacy = json.load(open(A.ROOT / "docs" / "abi_legacy_observations.json"))
    scores = next(o for o in legacy["observations"] if o["as_of"] == "2026-07-16")["factor_scores"]
    abi = A.composite(scores, A.weights(CFG))
    assert abi == pytest.approx(38.75) and A.label(abi, CFG)[0] == "HEALTHY"
    assert all(o["legacy_unverified"] for o in legacy["observations"])


def test_missing_factors_withhold_the_composite_and_labels_cover_0_to_100():
    scores = {k: 50 for k in CFG["factors"]}
    scores["eps_revisions"] = None
    assert A.composite(scores, A.weights(CFG)) is None
    assert A.composite(scores, A.weights(CFG, drop=("eps_revisions",))) == pytest.approx(50)
    assert A.label(0, CFG)[0] == "VERY_HEALTHY" and A.label(20, CFG)[0] == "VERY_HEALTHY" and A.label(20.01, CFG)[0] == "HEALTHY"
    assert A.label(75, CFG)[0] == "SPECULATIVE" and A.label(90.5, CFG)[0] == "EXTREME_BUBBLE" and A.label(100, CFG)[0] == "EXTREME_BUBBLE"


def fact(ticker, metric, start, end, val, filed, tag=None, accn="a"):
    return {"ticker": ticker, "metric": metric, "tag": tag or {"revenue": "Revenues", "capex": "PaymentsToAcquirePropertyPlantAndEquipment",
            "inventory": "InventoryNet"}[metric], "unit": "USD", "start": start, "end": end, "val": val, "accn": accn,
            "fy": None, "fp": None, "form": "10-Q", "filed": filed, "frame": None}


def test_capex_quarters_come_from_year_to_date_differences_and_respect_filing_dates():
    rows = [
        # fiscal year 2024: Q1 reported, then six- and nine-month and full-year cash-flow totals
        fact("X", "capex", "2024-01-01", "2024-03-31", 10, "2024-04-30"),
        fact("X", "capex", "2024-01-01", "2024-06-30", 25, "2024-07-30"),
        fact("X", "capex", "2024-01-01", "2024-09-30", 45, "2024-10-30"),
        fact("X", "capex", "2024-01-01", "2024-12-31", 70, "2025-02-01"),
    ]
    fund = A.Fundamentals(pd.DataFrame(rows), CFG)
    q = fund.flow_quarters("X", "capex", "2025-03-01", ["PaymentsToAcquirePropertyPlantAndEquipment"])
    assert q["value"].tolist() == [10, 15, 20, 25]
    early = fund.flow_quarters("X", "capex", "2024-08-15", ["PaymentsToAcquirePropertyPlantAndEquipment"])
    assert early["value"].tolist() == [10, 15]                      # the nine-month total was not filed yet


def test_a_restated_value_replaces_the_original_only_once_it_is_filed_and_the_preferred_tag_wins():
    rows = [fact("X", "revenue", "2024-01-01", "2024-03-31", 100, "2024-04-30"),
            fact("X", "revenue", "2024-01-01", "2024-03-31", 90, "2025-04-30"),
            fact("X", "revenue", "2024-01-01", "2024-03-31", 500, "2024-04-30", tag="SalesRevenueNet")]
    fund = A.Fundamentals(pd.DataFrame(rows), CFG)
    tags = ["Revenues", "SalesRevenueNet"]
    assert fund.flow_quarters("X", "revenue", "2024-12-31", tags)["value"].tolist() == [100]
    assert fund.flow_quarters("X", "revenue", "2025-05-01", tags)["value"].tolist() == [90]


def test_hyperscaler_factors_need_every_company_and_flag_shrinking_revenue():
    rows = []
    for t in ("MSFT", "AMZN", "GOOGL", "META"):
        for y, rev, cap in ((2024, 100, 10), (2025, 110, 15)):
            rows += [fact(t, "revenue", f"{y}-01-01", f"{y}-03-31", rev, f"{y}-04-30"), fact(t, "capex", f"{y}-01-01", f"{y}-03-31", cap, f"{y}-04-30")]
    fund = A.Fundamentals(pd.DataFrame(rows), CFG)
    f1, f2 = A.factor_capex(fund, CFG, "2025-05-15")
    assert f1["status"] == "OK" and f1["value"] == pytest.approx(0.5 / 0.1) and A.bucket(f1["value"], CFG["factors"]["capex_vs_revenue_growth"]["bands"]) == 100
    assert f2["value"] == pytest.approx(100 * 15 / 110)
    shrink = [dict(r, val=90) if r["metric"] == "revenue" and r["end"].startswith("2025") else r for r in rows]
    f1, _ = A.factor_capex(A.Fundamentals(pd.DataFrame(shrink), CFG), CFG, "2025-05-15")
    assert f1["status"] == "UNDEFINED" and f1["value"] is None
    f1, _ = A.factor_capex(A.Fundamentals(pd.DataFrame([r for r in rows if r["ticker"] != "META"]), CFG), CFG, "2025-05-15")
    assert f1["status"] == "INSUFFICIENT_DATA"


def test_inventory_build_is_inventory_growth_minus_revenue_growth_in_points():
    rows = []
    for t in ("NVDA", "AMD", "AVGO", "MU"):
        for y, rev, inv in ((2024, 100, 50), (2025, 120, 66)):
            rows += [fact(t, "revenue", f"{y}-01-01", f"{y}-03-31", rev, f"{y}-04-30"), fact(t, "inventory", None, f"{y}-03-31", inv, f"{y}-04-30")]
    f3 = A.factor_inventory(A.Fundamentals(pd.DataFrame(rows), CFG), CFG, "2025-06-01")
    assert f3["status"] == "OK" and f3["value"] == pytest.approx(100 * (0.32 - 0.20))


def test_official_concentration_sums_both_alphabet_classes():
    spy = pd.DataFrame({"ticker": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "XOM"],
                        "weight_pct": [7, 6, 7, 4, 2, 1.7, 3, 2, 1]})
    f4 = A.factor_concentration_official(spy, "as of x")
    assert f4["value"] == pytest.approx(32.7) and A.bucket(f4["value"], CFG["factors"]["mag7_concentration"]["bands"]) == 75
    assert A.factor_concentration_official(spy[spy["ticker"] != "TSLA"], None)["status"] == "INSUFFICIENT_DATA"


# ---------------- market factors ----------------
from abi import build as B  # noqa: E402
from abi import market as MK  # noqa: E402
import numpy as np  # noqa: E402


def daily_frame(prices: dict, start="2020-01-01"):
    rows = []
    for t, series in prices.items():
        for d, p in zip(pd.bdate_range(start, periods=len(series)), series):
            rows.append({"ticker": t, "date": d, "close": p, "adjclose": p, "close_unadj": p})
    return pd.DataFrame(rows)


def test_breadth_counts_members_above_their_200_day_average_and_skips_short_histories():
    up, down = list(np.linspace(100, 200, 260)), list(np.linspace(200, 100, 260))
    d = daily_frame({"A": up, "B": up, "C": down, "D": up[:150]})
    b = MK.breadth_series(d, ["A", "B", "C", "D"])
    last = b.iloc[-1]
    assert last["members_counted"] == 3 and last["above"] == 2 and last["pct_above"] == pytest.approx(200 / 3)
    assert last["members_listed"] == 4


def test_splits_only_count_between_the_filing_and_the_valuation_date():
    s = [{"date": "2021-07-20", "ratio": 4.0}, {"date": "2024-06-10", "ratio": 10.0}]
    assert MK.split_factor(s, pd.Timestamp("2021-01-01"), pd.Timestamp("2024-12-31")) == 40
    assert MK.split_factor(s, pd.Timestamp("2022-01-01"), pd.Timestamp("2024-06-09")) == 1
    assert MK.split_factor(s, pd.Timestamp("2024-06-10"), pd.Timestamp("2024-12-31")) == 1


def test_trailing_eps_sums_four_quarters_and_adjusts_for_later_splits():
    rows = []
    for end in ["2023-03-31", "2023-06-30", "2023-09-30", "2023-12-31"]:
        start = (pd.Timestamp(end) - pd.Timedelta(days=89)).date().isoformat()
        rows.append(fact("N", "eps_diluted", start, end, 10, "2024-02-01", tag="EarningsPerShareDiluted"))
    fund = A.Fundamentals(pd.DataFrame(rows), CFG)
    e = MK.ttm_eps(fund, "N", pd.Timestamp("2024-03-01"), [])
    assert e["eps"] == pytest.approx(40) and e["quarter_end"] == "2023-12-31"
    e = MK.ttm_eps(fund, "N", pd.Timestamp("2024-07-01"), [{"date": "2024-06-10", "ratio": 10.0}])
    assert e["eps"] == pytest.approx(4)                               # a 10-for-1 split after the filings
    assert MK.ttm_eps(fund, "N", pd.Timestamp("2024-01-15"), []) is None   # not filed yet


def test_pe_premium_needs_five_years_and_skips_negative_earnings():
    months = pd.date_range("2015-01-31", periods=80, freq="ME")
    h = pd.DataFrame({"month": months, "pe": [20.0] * 79 + [30.0]})
    p = MK.pe_premium(h, months[-1])
    assert p["status"] == "OK" and p["premium_pct"] == pytest.approx(50)
    assert MK.pe_premium(h, months[40])["status"] == "INSUFFICIENT_HISTORY"
    h.loc[79, "pe"] = None
    assert MK.pe_premium(h, months[-1])["status"] == "UNDEFINED"
    ok = {"A": pd.DataFrame({"month": months, "pe": [20.0] * 79 + [30.0]}), "B": h, "C": h}
    assert MK.factor_pe(ok, months[-1])["status"] == "UNDEFINED"        # one company left of three


def test_estimate_revision_blends_fiscal_years_into_next_twelve_months():
    a = pd.DataFrame([{"collected_on": "2026-10-09", "ticker": t, "period": p, "end_date": end, "current": cur, "d90": d90, "analysts": 30}
                      for t, end0, end1 in (("NVDA", "2027-01-31", "2028-01-31"), ("MSFT", "2027-06-30", "2028-06-30"))
                      for p, end, cur, d90 in (("0y", end0, 10.0, 10.0), ("+1y", end1, 12.0, 12.0))])
    r = MK.factor_revisions(a, pd.Timestamp("2026-10-09"))
    assert r["status"] == "OK" and all(v["same_fiscal_year_revision_pct"]["0y"] == 0 for v in r["companies"].values())
    assert r["value"] > 0                                            # rolling toward the larger next-year figure
    assert MK.factor_revisions(a, pd.Timestamp("2026-10-20"))["status"] == "STALE"
    assert MK.factor_revisions(a[a["ticker"] == "NVDA"], pd.Timestamp("2026-10-09"))["status"] == "INSUFFICIENT_DATA"


def test_drawdowns_and_forward_targets():
    p = list(np.linspace(100, 150, 300)) + list(np.linspace(150, 100, 100)) + list(np.linspace(100, 160, 300))
    d = daily_frame({"QQQ": p, "SOXX": p}, "2014-01-01")
    dds = B.drawdowns(d)
    assert len(dds) == 1 and dds[0]["depth_pct"] == pytest.approx(-33.3, abs=0.2)
    t = B.forward_targets(d)
    assert {"qqq_3m", "qqq_12m", "qqq_maxdd_12m", "soxx_12m"} <= set(t.columns)
    assert t["qqq_maxdd_12m"].dropna().min() == pytest.approx(-33.3, abs=0.5)


def test_contract_refuses_a_bubble_score_that_does_not_add_up():
    from publication.contract import ContractError, validate_ai_bubble
    good = {"automatic_execution_authorized": False, "legacy_observations": [{"legacy_unverified": True}],
            "current": {"research": {"abi": 38.75, "contributions": {"a": 30, "b": 8.75}, "missing": []}, "strict": {"abi": None},
                        "factors": [{"weight": 0.5}, {"weight": 0.5}]}}
    validate_ai_bubble(good)
    for bad in ({**good, "automatic_execution_authorized": True},
                {**good, "current": {**good["current"], "research": {"abi": 40, "contributions": {"a": 30}, "missing": []}}},
                {**good, "current": {**good["current"], "strict": {"abi": 30}}},
                {**good, "legacy_observations": [{"legacy_unverified": False}]}):
        with pytest.raises(ContractError):
            validate_ai_bubble(bad)
