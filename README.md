# Macro Intelligence Platform (MIHTS)

The Composite Recession Stress Index (RSI v2.0) and, later, a validated 12-month recession probability.
It is packaged into the Universal Investment Platform as the `macro` domain.

- Spec, frozen before any result: `docs/RSI_V2_SPEC.md` (executable form `config/rsi_v2.json`).
- Origin and history: `docs/HANDOFF_2026-10-09.md`. Earlier analyst readings are kept, unverified, in
  `docs/legacy_snapshots.json`.
- Run: `python run.py --fetch` downloads FRED and the S&P 500 into `data/snapshot/`. It computes the
  current reading, replays history from 1990 with release lags, evaluates it around NBER recessions,
  and writes `uip-package/` (`macro_uip_contract.json` plus its manifest).
- Production: `.github/workflows/macro-production.yml`, on weekdays after the 8:30 ET releases.
  It publishes the `macro-production-<run>` artifact the UIP imports.

The index informs; it never trades, allocates or decides a purchase.
