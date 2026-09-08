"""
Lineage must never attribute a published number to the wrong raw file.

The drawer that opens when you click a basket cell is the project's proof that
every figure traces back to stored bytes. If it can show a SIMULATED payload as
the origin of a LIVE median, the proof is worse than useless: it looks like
evidence while being wrong.

Two ways that happened, both fixed and both pinned here:
  - the Bronze lookup filtered on route and window but not source class
  - it took whichever record came first in the file, which on a day with a
    compliance refusal was a zero-byte refusal rather than the fetch that
    actually produced the fares
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

DB = Path(__file__).resolve().parents[1] / "apix.db"
pytestmark = pytest.mark.skipif(not DB.exists(), reason="run scripts.bootstrap first")


@pytest.fixture(scope="module")
def client():
    from webapp.backend.app import app
    return TestClient(app)


def _a_published_cell(client, source_class: str):
    latest = client.get(f"/public/apix/latest?source_class={source_class}").json()
    if not latest.get("available"):
        pytest.skip(f"no published {source_class} day")
    day = latest["observation_date"]
    basket = client.get(f"/public/basket").json()
    route = basket["routes"][0]["code"] if isinstance(basket.get("routes"), list) else "DEL-BOM"
    return day, route


@pytest.mark.parametrize("source_class", ["LIVE", "SIMULATED"])
def test_lineage_never_crosses_source_classes(client, source_class):
    """A LIVE cell is explained by LIVE bytes, and a SIMULATED cell by
    SIMULATED bytes. Mixing them would misattribute a real number to a
    generated file, or the reverse."""
    day, route = _a_published_cell(client, source_class)
    for window in (1, 7, 14, 21, 45):
        L = client.get(
            f"/public/lineage/{day}/{route}/{window}?source_class={source_class}"
        ).json()
        for rec in L["bronze"]:
            assert rec["source_class"] == source_class, (
                f"{source_class} cell {route} T+{window} was shown a "
                f"{rec['source_class']} payload from {rec['source_id']}"
            )


def test_the_payload_shown_first_is_the_one_that_was_parsed(client):
    """A cell can hold several attempts. The one the drawer leads with must be
    the fetch that produced fares, not a refusal or a timeout that produced
    nothing."""
    day, route = _a_published_cell(client, "LIVE")
    for window in (1, 7, 14, 21, 45):
        L = client.get(
            f"/public/lineage/{day}/{route}/{window}?source_class=LIVE"
        ).json()
        if not L["bronze"] or L["used_in_median"] == 0:
            continue
        first = L["bronze"][0]
        assert first["payload_bytes"] > 0, (
            f"{route} T+{window} has {L['used_in_median']} parsed fares but its "
            f"lineage leads with a {first['payload_bytes']}-byte "
            f"{first['fetch_status']} record"
        )


def test_the_median_count_matches_the_engine(client):
    """used_in_median is what the drawer prints to explain the published
    figure. The engine takes the median over every OK fare, flagged ones
    included, so counting them out here would describe a calculation nobody
    performed."""
    day, route = _a_published_cell(client, "LIVE")
    for window in (1, 7, 14, 21, 45):
        L = client.get(
            f"/public/lineage/{day}/{route}/{window}?source_class=LIVE"
        ).json()
        gold = L.get("gold")
        if not gold or gold.get("n_used") is None:
            continue
        assert L["used_in_median"] == gold["n_used"], (
            f"{route} T+{window}: drawer says {L['used_in_median']} fares, "
            f"engine used {gold['n_used']}"
        )
