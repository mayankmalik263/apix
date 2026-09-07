"""
Live adapter: Cleartrip.

This is the adapter that makes APIx touch reality. Everything else in the
pipeline can run on simulated history; this one produces real Indian domestic
airfares, captured from a source whose robots.txt permits the fare-search path.

HOW IT WORKS
------------
The fare page is a JavaScript application, so there is no server-rendered price
to scrape. Instead we open the page in a real browser and intercept the XHR the
page itself makes to its own fare API. That response is already structured JSON
with the fare split into base / tax / total -- which is both far more reliable
than parsing rendered HTML, and much gentler on the source: one page load, one
search, no crawling.

COMPLIANCE
----------
- robots.txt permits /flights and /flights/results for our user agent.
  Verified by apix.collect.compliance, and re-verified every collection day.
- The runner refuses to call this adapter at all unless today's verdict is
  PERMITTED. The gate fires before the browser is even launched.
- Identifiable user agent carrying a contact address.
- One request per cell, rate limited by the runner.
- No CAPTCHA handling. No IP rotation. If we are blocked, we record BLOCKED
  and stop -- that is the finding, not an obstacle.

WHAT GOES TO BRONZE
-------------------
The intercepted JSON, verbatim, with its SHA-256. Not our parse of it. When the
parser breaks -- and a site's JSON shape will change -- the raw archive lets the
whole history be re-parsed. A parsed-only archive would lose those days forever.
"""
from __future__ import annotations

import json
from datetime import date

from apix.collect.base import RawResponse, SourceAdapter
from apix.config import departure_date, load_registry
from apix.vocab import ObsStatus, SourceClass

BASE = "https://www.cleartrip.com"
SEARCH_PAGE = BASE + "/flights/results"
# The page's own fare API. We do not construct or call this ourselves -- we
# observe the request the page makes and read the response.
FARE_API_MARKER = "flight/search/v2"

PAGE_TIMEOUT_MS = 60_000
FARE_WAIT_MS = 22_000


def search_url(origin: str, destination: str, dep: date) -> str:
    return (
        f"{SEARCH_PAGE}?adults=1&childs=0&infants=0&class=Economy"
        f"&depart_date={dep.strftime('%d%%2F%m%%2F%Y')}"
        f"&from={origin}&to={destination}&intl=n&sd=1"
    )


class CleartripAdapter(SourceAdapter):
    source_id = "cleartrip"
    source_class = SourceClass.LIVE

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.user_agent = load_registry()["etiquette"]["user_agent"]

    def search(
        self, route_code: str, window_days: int, observation_date: date
    ) -> RawResponse:
        origin, destination = route_code.split("-")
        dep = departure_date(observation_date, window_days)
        url = search_url(origin, destination, dep)

        common = dict(
            source_id=self.source_id,
            source_class=self.source_class,
            observation_date=observation_date,
            route_code=route_code,
            window_days=window_days,
            departure_date=dep,
            request_url=url,
            user_agent=self.user_agent,
        )

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return RawResponse(
                fetch_status=ObsStatus.FETCH_FAIL,
                error_detail="playwright not installed", **common,
            )

        captured: dict[str, str] = {}
        status_code: dict[str, int] = {}

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                ctx = browser.new_context(
                    user_agent=self.user_agent,
                    locale="en-IN",
                    viewport={"width": 1400, "height": 900},
                )
                page = ctx.new_page()

                def on_response(resp):
                    # Keep the LAST fare response: the page may fire an initial
                    # request and then a refined one.
                    try:
                        if FARE_API_MARKER in resp.url and resp.status == 200:
                            captured["body"] = resp.text()
                            status_code["code"] = resp.status
                    except Exception:
                        pass

                page.on("response", on_response)
                page.goto(url, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
                page.wait_for_timeout(FARE_WAIT_MS)

                # Bot walls and challenge pages: detect, record, never defeat.
                try:
                    head = (page.inner_text("body") or "")[:400].lower()
                except Exception:
                    head = ""
                browser.close()

            if not captured:
                if any(w in head for w in ("captcha", "are you a human",
                                           "access denied", "unusual traffic",
                                           "verify you are")):
                    return RawResponse(
                        fetch_status=ObsStatus.BLOCKED,
                        http_status=403,
                        error_detail="challenge page encountered; not bypassed by design",
                        **common,
                    )
                return RawResponse(
                    fetch_status=ObsStatus.FETCH_FAIL,
                    error_detail="no fare payload observed within the wait window",
                    **common,
                )

            body = captured["body"]
            # An empty result set is a market fact, not a failure.
            try:
                parsed = json.loads(body)
                if not parsed.get("fares"):
                    return RawResponse(
                        fetch_status=ObsStatus.SOLD_OUT,
                        http_status=status_code.get("code", 200),
                        payload=body,
                        **common,
                    )
            except json.JSONDecodeError:
                return RawResponse(
                    fetch_status=ObsStatus.PARSE_FAIL,
                    http_status=status_code.get("code", 200),
                    payload=body,
                    error_detail="fare payload was not valid JSON",
                    **common,
                )

            return RawResponse(
                fetch_status=ObsStatus.OK,
                http_status=status_code.get("code", 200),
                payload=body,
                **common,
            )

        except Exception as exc:
            return RawResponse(
                fetch_status=ObsStatus.FETCH_FAIL,
                error_detail=f"{type(exc).__name__}: {str(exc)[:300]}",
                **common,
            )


# ---------------------------------------------------------------------------
# Reference parser.
#
# Lives here beside the adapter because the shape it reads is the shape this
# adapter captures. Bharat's Silver layer calls this; if the site changes, this
# function is the only thing that needs fixing, and Bronze lets the whole
# history be re-parsed afterwards.
# ---------------------------------------------------------------------------
def parse_quotes(payload: str) -> list[dict]:
    """Cleartrip fare payload -> the quote list the Silver loader expects.

    Validated against a live capture: the minimum total this returns for
    DEL-BOM on 2026-09-24 was 6090, matching the cheapest fare the page itself
    displayed.
    """
    data = json.loads(payload)
    fares = data.get("fares") or {}
    out = []

    for fare_id, fare in fares.items():
        try:
            pricing = fare["pricing"]["totalPricing"]
            total = float(pricing["totalPrice"])
        except (KeyError, TypeError, ValueError):
            continue
        if total <= 0:
            continue

        tax = _num(pricing.get("totalTax"))
        base = _num(pricing.get("totalBaseFare"))
        # Cleartrip reports base + tax; anything unaccounted for is a fee.
        fees = None
        if base is not None and tax is not None:
            fees = round(total - base - tax, 2)
            if abs(fees) < 0.5:
                fees = 0.0

        # fareId encodes: REGULAR__<date>__<airlines>__<airlines>__DEL_BOM__
        #                 ...__<cabin>__DOM__OW__...
        parts = fare_id.split("__")
        carrier = None
        if len(parts) > 2 and parts[2]:
            carrier = parts[2].split("^")[0][:8] or None

        out.append(
            {
                "carrier": carrier,
                "flight_no": None,   # not carried on the fare object
                "departure_time": None,
                "stops": None,
                "base_fare": base,
                "taxes": tax,
                "fees": fees,
                "total_fare": total,
                "currency": "INR",
                # Full id, not truncated. The first 64 characters are common to
                # ~10 fares each, so truncating here collapsed 226 distinct
                # quotes into 21 and moved the cell median by +52%.
                "fare_ref": fare_id,
            }
        )
    return out


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
