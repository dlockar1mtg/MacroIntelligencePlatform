"""Nasdaq-100 member list for the breadth input of the AI / Technology Bubble Index (synthetic tickers)."""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pytest

from abi import collect

TICKERS = [f"T{chr(65 + i // 26)}{chr(65 + i % 26)}" for i in range(101)]  # 101 synthetic tickers


def table(tickers, table_id="constituents"):
    rows = "".join(f"<tr><td>{t}</td><td>Company {t}</td></tr>" for t in tickers)
    return f'<table class="wikitable" id="{table_id}"><tr><th>Ticker</th><th>Company</th></tr>{rows}</table>'


class FakeFetcher:
    def __init__(self, pages: dict):
        self.pages, self.asked = pages, []

    def get(self, url, headers=None, timeout=40):
        self.asked.append(url)
        page = self.pages.get(url)
        if page is None or isinstance(page, Exception):
            raise page or RuntimeError(f"HTTP 403 for {url}")
        return page.encode()


def snapshot(tmp_path, as_of="2026-11-23", tickers=TICKERS) -> Path:
    p = tmp_path / "snap.json"
    p.write_text(json.dumps({"as_of": as_of, "source": "test", "tickers": tickers}))
    return p


def test_members_come_from_the_new_wikipedia_list_page(tmp_path):
    f = FakeFetcher({collect.NDX_LIST_URL: "<html>" + table(TICKERS) + "</html>"})
    out = collect.ndx_members(f, snapshot=snapshot(tmp_path))
    assert len(out) == 101 and out.attrs["source"].startswith("Wikipedia List of NASDAQ-100 companies")


def test_the_old_article_is_still_tried(tmp_path):
    f = FakeFetcher({collect.NDX_URL: "<html>" + table(TICKERS, table_id="x") + "</html>"})
    out = collect.ndx_members(f, snapshot=snapshot(tmp_path))
    assert out.attrs["source"].startswith("Wikipedia Nasdaq-100 article")


def test_article_without_a_members_table_falls_back_to_a_recent_snapshot(tmp_path):
    f = FakeFetcher({collect.NDX_LIST_URL: "<html><table><tr><td>1</td></tr></table></html>",
                     collect.NDX_URL: "<html><table><tr><td>Year</td></tr></table></html>"})
    out = collect.ndx_members(f, snapshot=snapshot(tmp_path), today=date(2026, 12, 1))
    assert len(out) == 101 and out.attrs["source"].startswith("committed snapshot as of 2026-11-23 (8 days old)")
    assert "nasdaq api" in out.attrs["fallback_errors"]


def test_an_old_snapshot_is_refused(tmp_path):
    with pytest.raises(RuntimeError, match="days old"):
        collect.ndx_members(FakeFetcher({}), snapshot=snapshot(tmp_path, as_of="2025-01-01"), today=date(2026, 11, 23))


def test_committed_snapshot_is_valid():
    snap = json.loads(collect.NDX_SNAPSHOT.read_text(encoding="utf-8"))
    assert 95 <= len(snap["tickers"]) <= 110 and len(set(snap["tickers"])) == len(snap["tickers"])
    date.fromisoformat(snap["as_of"])
