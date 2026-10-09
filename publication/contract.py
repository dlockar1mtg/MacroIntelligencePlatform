"""macro_uip_contract.json: the versioned file the UIP imports, plus its manifest and validation."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

CONTRACT_VERSION = "1.0.0"
BANDS = {"EXPANSION", "LATE_CYCLE", "DETERIORATION", "RECESSIONARY_STRESS", "PANIC"}


class ContractError(ValueError):
    pass


def build_contract(*, current: dict, history: list[dict], evaluation: dict, legacy: list[dict], freshness: dict,
                   cfg: dict, source_commit: str, run_id: str | None, generated_at: str | None = None) -> dict:
    return {
        "contract_version": CONTRACT_VERSION, "domain": "macro", "model_id": cfg["model_id"], "model_version": cfg["model_version"],
        "generated_at_utc": generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_repository": "dlockar1mtg/MacroIntelligencePlatform", "source_commit": source_commit, "source_run_id": run_id,
        "certification_status": "PROVISIONAL",
        "current": current,
        "weights": {k: {"weight": s["weight"], "components": {c: v["weight"] for c, v in s["components"].items()}}
                    for k, s in cfg["systems"].items()},
        "anchors": {c: {"expansion": v["expansion"], "stress": v["stress"], "unit": v["unit"], "series": v["series"]}
                    for s in cfg["systems"].values() for c, v in s["components"].items()},
        "bands": cfg["bands"], "bands_status": cfg["bands_status"],
        "history": history, "evaluation": evaluation,
        "legacy_snapshots": legacy, "data_freshness": freshness,
        "recession_probability": cfg["recession_probability"],
        "asset_environment": {"status": "NOT_PUBLISHED", "why": "phase 5; needs valuation and forward-return inputs"},
        "housing_opportunity": {"status": "REUSES_HOUSING_PLATFORM", "why": "owner decision 2026-10-09"},
        "automatic_execution_authorized": False,
    }


def validate_contract(c: dict) -> None:
    if c.get("domain") != "macro" or not str(c.get("contract_version", "")).startswith("1."):
        raise ContractError("domain or contract version")
    if c.get("automatic_execution_authorized") is not False:
        raise ContractError("automatic execution must be false")
    if c.get("recession_probability", {}).get("status") == "PUBLISHED" and not c["recession_probability"].get("calibration"):
        raise ContractError("a recession probability needs its calibration evidence")
    rp = c.get("recession_probability") or {}
    if rp.get("status") == "PUBLISHED":
        p = rp.get("probability_12m")
        if not isinstance(p, (int, float)) or not 0 <= p <= 1 or not (rp.get("calibration") or {}).get(rp.get("chosen_model") or ""):
            raise ContractError("a published recession probability needs a 0-1 value and calibration for its chosen model")
    dq = c.get("data_quality")
    if dq is not None and dq.get("status") not in ("OK", "DEGRADED"):
        raise ContractError("data_quality status must be OK or DEGRADED")
    cur = c.get("current") or {}
    if cur.get("rsi") is not None:
        if not -1 <= float(cur["rsi"]) <= 1 or cur.get("band") not in BANDS:
            raise ContractError("rsi out of range or unknown band")
        total = sum(r["contribution"] for r in cur["components"])
        if abs(total - cur["rsi"]) > 0.002:
            raise ContractError(f"contributions sum to {total:.4f}, not the rsi {cur['rsi']}")
    if abs(sum(s["weight"] for s in c["weights"].values()) - 1) > 1e-9:
        raise ContractError("system weights must sum to 1")
    if any(not s.get("legacy_unverified") for s in c.get("legacy_snapshots") or []):
        raise ContractError("legacy snapshots must stay marked unverified")
    validate_ai_bubble(c.get("ai_bubble"))
    for h in c.get("history") or []:
        if h.get("rsi") is not None and not -1 <= h["rsi"] <= 1:
            raise ContractError("history rsi out of range")


def validate_ai_bubble(ab: dict | None) -> None:
    if not ab:
        return
    if ab.get("automatic_execution_authorized") is not False:
        raise ContractError("ai_bubble must not authorize automatic execution")
    if ab.get("status") == "FAILED":
        return
    cur = ab.get("current") or {}
    r = cur.get("research") or {}
    if r.get("abi") is not None:
        if not 0 <= float(r["abi"]) <= 100:
            raise ContractError("ai_bubble research abi out of range")
        if abs(sum(v for v in r["contributions"].values() if v is not None) - float(r["abi"])) > 0.01:
            raise ContractError("ai_bubble contributions do not add up to the index")
        if r.get("missing"):
            raise ContractError("ai_bubble published with missing factors")
    if (cur.get("strict") or {}).get("abi") is not None:
        raise ContractError("strict v1.0 stays blocked until licensed consensus data exists")
    if any(not o.get("legacy_unverified") for o in ab.get("legacy_observations") or []):
        raise ContractError("legacy ai_bubble readings must stay marked unverified")
    if abs(sum(f["weight"] for f in cur.get("factors") or []) - 1) > 1e-9 and cur.get("factors"):
        raise ContractError("ai_bubble weights must sum to 1")


def write_package(directory: Path, contract: dict) -> dict:
    validate_contract(contract)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    text = json.dumps(contract, indent=1) + "\n"
    (directory / "macro_uip_contract.json").write_text(text, encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    manifest = {"package_id": f"macro-{contract['generated_at_utc'][:10]}-{digest[:12]}", "domain": "macro",
                "contract_version": contract["contract_version"], "generated_at_utc": contract["generated_at_utc"],
                "repository_commit": contract["source_commit"],
                "files": [{"path": "macro_uip_contract.json", "sha256": digest, "row_count": len(contract["history"])}],
                "validation_status": "PASS", "certification_status": contract["certification_status"],
                "automatic_execution_authorized": False}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    return manifest


def validate_package(directory: Path) -> dict:
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    for f in manifest["files"]:
        if hashlib.sha256((directory / f["path"]).read_bytes()).hexdigest() != f["sha256"]:
            raise ContractError(f"digest mismatch for {f['path']}")
    contract = json.loads((directory / "macro_uip_contract.json").read_text(encoding="utf-8"))
    validate_contract(contract)
    return contract
