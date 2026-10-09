"""Compute RSI v2.0 now and through history, evaluate it, and build the UIP package.

Usage: python run.py [--snapshot data/snapshot] [--fetch] [--package uip-package] [--since 1990-01]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

import pandas as pd

from abi import build as ABI
from abi import engine as ABI_ENGINE
from macro import data as D
from macro import evaluate as E
from macro import recession_model as M
from macro import rsi as R
from publication.contract import build_contract, validate_ai_bubble, validate_package, write_package

ROOT = Path(__file__).resolve().parent


def commit() -> str:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "0000000"


def data_quality(snapshot: Path, cfg: dict, current: dict) -> dict:
    """Did this run's fetch actually refresh the inputs? A failed download leaves yesterday's file in place, so the
    reading would look current while resting on old data: say so in the package (DEGRADED) instead."""
    mpath = Path(snapshot) / "MANIFEST.json"
    man = json.loads(mpath.read_text()) if mpath.exists() else {}
    rsi_series = {c["series"] for s in cfg["systems"].values() for c in s["components"].values()}
    errors = {k: v["error"] for k, v in (man.get("series") or {}).items() if isinstance(v, dict) and v.get("error")}
    failed_rsi = sorted(k for k in errors if k in rsi_series)
    stale = sorted(c["component"] for c in current.get("components") or [] if c.get("status") in ("STALE", "MISSING"))
    return {"status": "DEGRADED" if failed_rsi else "OK", "fetched_at_utc": man.get("taken_at_utc"),
            "failed_series": failed_rsi, "other_fetch_errors": {k: v for k, v in errors.items() if k not in rsi_series},
            "stale_components": stale,
            "why": (f"these index inputs could not be refreshed this run and use the last good download: {', '.join(failed_rsi)}" if failed_rsi else None)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--snapshot", type=Path, default=ROOT / "data" / "snapshot")
    p.add_argument("--fetch", action="store_true", help="download fresh data into --snapshot first")
    p.add_argument("--package", type=Path, default=ROOT / "uip-package")
    p.add_argument("--outputs", type=Path, default=ROOT / "outputs")
    p.add_argument("--since", default="1990-01")
    p.add_argument("--notice", action="store_true")
    p.add_argument("--abi", type=Path, default=ROOT / "data" / "abi", help="AI bubble index inputs (from python -m abi.collect)")
    p.add_argument("--abi-archive", type=Path, default=ROOT / "state" / "abi_estimates.csv")
    a = p.parse_args(argv)
    if a.fetch:
        print(json.dumps(D.save_snapshot(a.snapshot)["series"], indent=1))
    cfg = R.load_config()
    data = D.load_snapshot(a.snapshot)
    now = max(data.dropna(how="all").index)
    current = R.compute(data, now, cfg)
    hist = R.history(data, a.since, str(now), cfg)
    evaluation = E.evaluate(hist, data, a.since)
    legacy = E.legacy_comparison(hist)
    full = R.history(data, "1975-01", str(now), cfg)          # the RSI replay as M3's input (1990+ has full coverage)
    probability = M.build(data, full) if {"GS10", "TB3MS", "BAA"} <= set(data.columns) else None
    a.outputs.mkdir(parents=True, exist_ok=True)
    hist.to_csv(a.outputs / "rsi_history.csv", index=False)
    (a.outputs / "rsi_current.json").write_text(json.dumps(current, indent=1) + "\n", encoding="utf-8")
    (a.outputs / "rsi_evaluation.json").write_text(json.dumps({"evaluation": evaluation, "legacy": legacy}, indent=1) + "\n", encoding="utf-8")
    rec = set(str(m) for m in data["USREC"].dropna().index[data["USREC"].dropna() == 1])
    history = [{"month": r.month, "rsi": None if pd.isna(r.rsi) else float(r.rsi), "band": r.band if isinstance(r.band, str) else None,
                "coverage": float(r.coverage), "recession": r.month in rec} for r in hist.itertuples()]
    freshness = D.latest_observations(a.snapshot)
    contract = build_contract(current=current, history=history, evaluation=evaluation, legacy=legacy, freshness=freshness,
                              cfg=cfg, source_commit=commit(), run_id=os.environ.get("GITHUB_RUN_ID"))
    contract["data_quality"] = data_quality(a.snapshot, cfg, current)
    if probability is not None:
        contract["recession_probability"] = probability
        (a.outputs / "recession_probability.json").write_text(json.dumps(probability, indent=1) + "\n", encoding="utf-8")
    if (a.abi / "MANIFEST.json").exists():
        try:
            section = ABI.section(ABI.Inputs(a.abi, a.abi_archive, ABI_ENGINE.load_config()))
            validate_ai_bubble(section)                  # checked and serialized here, so it can never block the RSI package
            text = json.dumps(section, indent=1)
        except Exception as exc:  # noqa: BLE001 - the bubble index never blocks the RSI package
            section = {"status": "FAILED", "why": f"{type(exc).__name__}: {str(exc)[:300]}", "automatic_execution_authorized": False}
            text = json.dumps(section, indent=1)
        contract["ai_bubble"] = section
        (a.outputs / "abi.json").write_text(text + "\n", encoding="utf-8")
    manifest = write_package(a.package, contract)
    validate_package(a.package)
    summary = {"package_id": manifest["package_id"], "as_of": current["as_of_month"], "rsi": current["rsi"], "band": current["band"],
               "coverage": current["coverage"], "systems": {k: v["score"] for k, v in current["systems"].items()},
               "recessions": [(e["recession_start"], e["lead_months"], e["max_in_24_before"]) for e in evaluation["recessions"]],
               "false_alarms": len(evaluation["false_alarms"]),
               "recession_probability": None if probability is None else {k: probability.get(k) for k in ("status", "chosen_model", "probability_12m", "as_of_month")}}
    ab = contract.get("ai_bubble") or {}
    summary["ai_bubble"] = (ab.get("current") or {}).get("research") or ab.get("status")
    print(json.dumps(summary))
    if a.notice:
        print(f"::notice title=RSI v2.0::{current['as_of_month']} RSI {current['rsi']} {current['band']} coverage {current['coverage']} | "
              + ", ".join(f"{k} {v['score']}" for k, v in current["systems"].items()))
        for e in evaluation["recessions"]:
            print(f"::notice title=Recession {e['recession_start']}::12 months before {e['rsi_12_months_before']}, lead at 0.2: {e['lead_months']} months, max {e['max_in_24_before']}")
        print(f"::notice title=False alarms::{json.dumps(evaluation['false_alarms'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
