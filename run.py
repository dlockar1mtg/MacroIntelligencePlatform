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

from macro import data as D
from macro import evaluate as E
from macro import rsi as R
from publication.contract import build_contract, validate_package, write_package

ROOT = Path(__file__).resolve().parent


def commit() -> str:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "0000000"


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--snapshot", type=Path, default=ROOT / "data" / "snapshot")
    p.add_argument("--fetch", action="store_true", help="download fresh data into --snapshot first")
    p.add_argument("--package", type=Path, default=ROOT / "uip-package")
    p.add_argument("--outputs", type=Path, default=ROOT / "outputs")
    p.add_argument("--since", default="1990-01")
    p.add_argument("--notice", action="store_true")
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
    manifest = write_package(a.package, contract)
    validate_package(a.package)
    summary = {"package_id": manifest["package_id"], "as_of": current["as_of_month"], "rsi": current["rsi"], "band": current["band"],
               "coverage": current["coverage"], "systems": {k: v["score"] for k, v in current["systems"].items()},
               "recessions": [(e["recession_start"], e["lead_months"], e["max_in_24_before"]) for e in evaluation["recessions"]],
               "false_alarms": len(evaluation["false_alarms"])}
    print(json.dumps(summary))
    if a.notice:
        print(f"::notice title=RSI v2.0::{current['as_of_month']} RSI {current['rsi']} {current['band']} coverage {current['coverage']} | "
              + ", ".join(f"{k} {v['score']}" for k, v in current["systems"].items()))
        for e in evaluation["recessions"]:
            print(f"::notice title=Recession {e['recession_start']}::12 months before {e['rsi_12_months_before']}, lead at 0.2: {e['lead_months']} months, max {e['max_in_24_before']}")
        print(f"::notice title=False alarms::{json.dumps(evaluation['false_alarms'])}")
        for c in current["components"]:
            if c["status"] not in ("OK", "FLOORED_AFTER_INVERSION"):
                print(f"::warning title=RSI {c['component']}::{c['status']} ({c['series']}, last {c['observation_month']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
