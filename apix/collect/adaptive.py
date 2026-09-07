"""
Adaptive fare parsing, built on Scrapling's Selector.

WHY THIS EXISTS
    The problem statement names it directly: "page-structure changes silently
    breaking the parser". A CSS selector written against today's markup is a
    time bomb -- the site ships a redesign, the selector matches nothing, and
    the series quietly fills with PARSE_FAIL until somebody notices.

    Scrapling's Selector can re-find an element by its shape and context rather
    than by a class name someone else controls. We store what an element looked
    like when it worked; when the literal selector stops matching, we relocate
    it instead of failing.

WHAT THIS MODULE DOES NOT USE
    Scrapling also ships Fetcher, DynamicFetcher and StealthyFetcher. Those
    pull in curl_cffi (TLS fingerprint impersonation) and patchright (a
    Playwright fork built to defeat bot detection). Neither is installed.

    Fetching stays on plain Playwright with the identifiable user agent from
    compliance/registry.yml. Scrapling is used here purely as a parser —
    nothing in this module makes a network request.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from scrapling.parser import Selector

# "₹6,090", "INR 6090", "6,090.00", "Rs. 6090"
_MONEY = re.compile(r"(?:₹|rs\.?|inr)?\s*([\d][\d,]*(?:\.\d{1,2})?)", re.I)
# A domestic economy one-way fare below this is a fragment, above it is a
# different product. Bounds, not cleaning: anything outside is reported, not
# quietly coerced.
FARE_MIN, FARE_MAX = 800.0, 400_000.0


def parse_money(text: str | None) -> float | None:
    """'₹6,090' -> 6090.0. Returns None rather than guessing."""
    if not text:
        return None
    m = _MONEY.search(str(text))
    if not m:
        return None
    try:
        v = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return v if FARE_MIN <= v <= FARE_MAX else None


@dataclass
class FareShape:
    """What a fare row looked like on a page we successfully parsed.

    Persisted alongside the adapter so a redesign is recoverable: the literal
    selector is tried first, and the remembered shape is the fallback.
    """
    card_selector: str
    price_selector: str
    airline_selector: str | None = None
    flight_no_selector: str | None = None
    notes: str = ""


@dataclass
class ParseOutcome:
    quotes: list[dict] = field(default_factory=list)
    strategy: str = "none"          # literal | relocated | similar | none
    detail: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.quotes)


def _text(node, selector: str | None) -> str | None:
    """Text content, whether or not the caller remembered '::text'.

    Without this a selector like 'span.al' returns the element's markup rather
    than its text, and a carrier comes out as '<span class="al">IndiGo</span>'.
    Normalising here means the shape definitions stay readable.
    """
    if not selector:
        return None
    sel = selector if "::" in selector else selector + "::text"
    for attempt in (sel, selector):
        try:
            hit = node.css(attempt)
        except Exception:
            continue
        if hit:
            val = str(hit[0]).strip()
            if val and "<" not in val:
                return val
    return None


def _quotes_from_cards(cards, shape: FareShape, source_id: str) -> list[dict]:
    out: list[dict] = []
    for i, card in enumerate(cards):
        total = parse_money(_text(card, shape.price_selector))
        if total is None:
            continue
        out.append({
            "carrier": _text(card, shape.airline_selector),
            "flight_no": _text(card, shape.flight_no_selector),
            "departure_time": None,
            "stops": None,
            "base_fare": None,
            "taxes": None,
            "fees": None,
            "total_fare": total,
            "currency": "INR",
            # Position is the only stable identity an HTML card has once the
            # site's own ids are gone. Enough to keep two identical fares apart.
            "fare_ref": f"{source_id}#card{i}:{total:.0f}",
        })
    return out


def parse_fares(html: str, shape: FareShape, source_id: str = "html") -> ParseOutcome:
    """Three attempts, in order, each one weaker than the last.

    1. The literal selector. Fast, and right until the site changes.
    2. Relocate: find the element the selector USED to match, by shape.
    3. find_similar: given one card we can still identify, find its siblings.

    Which one worked is returned, because "we parsed it, but only by falling
    back" is information the operator should have before the parser dies
    completely tomorrow.
    """
    if not html or not html.strip():
        return ParseOutcome(strategy="none", detail="empty document")

    try:
        page = Selector(html)
    except Exception as exc:
        return ParseOutcome(strategy="none", detail=f"unparseable: {type(exc).__name__}")

    # 1 -- the literal selector
    try:
        cards = page.css(shape.card_selector)
    except Exception:
        cards = []
    if cards:
        q = _quotes_from_cards(cards, shape, source_id)
        if q:
            return ParseOutcome(q, "literal", f"{len(cards)} cards matched {shape.card_selector!r}")

    # 2 -- the selector matched nothing. Ask Scrapling to relocate by shape.
    try:
        anchor = page.css_first(shape.card_selector)
        if anchor is not None:
            similar = anchor.find_similar()
            cards = [anchor, *similar]
            q = _quotes_from_cards(cards, shape, source_id)
            if q:
                return ParseOutcome(q, "similar",
                                    f"literal selector matched 1; find_similar recovered "
                                    f"{len(cards)} cards")
    except Exception:
        pass

    # 3 -- find any element whose text reads like a fare, then take its parents
    #      as the cards. Last resort, and it says so.
    try:
        priced = [n for n in page.css("*") if parse_money(str(n.text)) is not None
                  and len(str(n.text)) < 24]
        seen, q = set(), []
        for i, n in enumerate(priced):
            v = parse_money(str(n.text))
            if v is None or v in seen:
                continue
            seen.add(v)
            q.append({"carrier": None, "flight_no": None, "departure_time": None,
                      "stops": None, "base_fare": None, "taxes": None, "fees": None,
                      "total_fare": v, "currency": "INR",
                      "fare_ref": f"{source_id}#text{i}:{v:.0f}"})
        if q:
            return ParseOutcome(q, "relocated",
                                f"selectors failed entirely; recovered {len(q)} fares by "
                                f"text shape -- THE PARSER NEEDS UPDATING")
    except Exception as exc:
        return ParseOutcome(strategy="none", detail=f"recovery failed: {type(exc).__name__}")

    return ParseOutcome(strategy="none", detail="no fare-shaped content found")
