"""
The parser must survive a site redesign.

"Page-structure changes silently breaking the parser" is named as a risk in the
problem statement, and the honest answer is not "it won't happen" -- it is that
when it happens the system degrades in a way an operator can see.

These tests rename every class on the page and check we still recover fares,
and that the outcome says HOW it recovered, so a fallback never passes silently
as a healthy parse.
"""
from __future__ import annotations

import pytest

from apix.collect.adaptive import FareShape, parse_fares, parse_money

TODAY = """
<div class="results">
  <div class="fare-card"><span class="al">IndiGo</span><span class="amt">&#8377;6,090</span></div>
  <div class="fare-card"><span class="al">Air India</span><span class="amt">&#8377;7,675</span></div>
  <div class="fare-card"><span class="al">Vistara</span><span class="amt">&#8377;24,056</span></div>
</div>"""

# Same page, after a redesign. Every class name has changed.
REDESIGNED = """
<div class="srp-results-v2">
  <div class="flightRow__container"><span class="carrierName">IndiGo</span>
    <span class="priceTag">&#8377;6,090</span></div>
  <div class="flightRow__container"><span class="carrierName">Air India</span>
    <span class="priceTag">&#8377;7,675</span></div>
  <div class="flightRow__container"><span class="carrierName">Vistara</span>
    <span class="priceTag">&#8377;24,056</span></div>
</div>"""

SHAPE = FareShape(card_selector="div.fare-card", price_selector="span.amt",
                  airline_selector="span.al")


def test_parses_todays_markup():
    r = parse_fares(TODAY, SHAPE, "test")
    assert r.ok
    assert r.strategy == "literal"
    assert [q["total_fare"] for q in r.quotes] == [6090.0, 7675.0, 24056.0]
    assert [q["carrier"] for q in r.quotes] == ["IndiGo", "Air India", "Vistara"]


def test_survives_a_full_redesign():
    """Every selector in SHAPE now matches nothing. We must still get fares,
    and the strategy must say we fell back."""
    r = parse_fares(REDESIGNED, SHAPE, "test")
    assert r.ok, "a redesign silently produced zero fares"
    assert r.strategy != "literal", "claimed a clean parse against changed markup"
    assert sorted(q["total_fare"] for q in r.quotes) == [6090.0, 7675.0, 24056.0]
    assert "NEEDS UPDATING" in r.detail or r.strategy == "similar"


def test_a_page_with_no_fares_is_not_invented():
    r = parse_fares("<div class='results'><p>No flights found</p></div>", SHAPE, "test")
    assert not r.ok
    assert r.quotes == []


def test_empty_and_broken_input_do_not_raise():
    for bad in ("", "   ", "<<<not html", "{\"json\": true}"):
        r = parse_fares(bad, SHAPE, "test")
        assert not r.ok


def test_fares_are_kept_distinct_even_at_the_same_price():
    """Two flights at the same price are two observations, not one. This is the
    bug that truncating the Cleartrip fare id caused on real data."""
    html = """<div class="results">
      <div class="fare-card"><span class="al">6E</span><span class="amt">&#8377;5,499</span></div>
      <div class="fare-card"><span class="al">6E</span><span class="amt">&#8377;5,499</span></div>
    </div>"""
    r = parse_fares(html, SHAPE, "test")
    assert len(r.quotes) == 2
    assert len({q["fare_ref"] for q in r.quotes}) == 2


@pytest.mark.parametrize("text,expected", [
    ("₹6,090", 6090.0), ("Rs. 7675", 7675.0), ("INR 24,056.00", 24056.0),
    ("6090", 6090.0), ("₹1,23,456", 123456.0),
])
def test_money_formats_indian_sites_actually_use(text, expected):
    assert parse_money(text) == expected


@pytest.mark.parametrize("text", [None, "", "Free", "₹12", "₹9,99,99,999", "seat 6A"])
def test_money_that_is_not_a_fare_returns_none(text):
    """Out-of-range values are reported as unparseable rather than coerced. A
    12-rupee 'fare' is a fragment of something else."""
    assert parse_money(text) is None
