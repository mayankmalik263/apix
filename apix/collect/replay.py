"""
Replay adapter -- seeded synthetic history.

WHY THIS EXISTS
---------------
APIx measures a quantity that can only be collected forward in time. A fare on
15 August 2026 cannot be retrieved on 2 September 2026. With days of runway
before a demo, a prototype either shows one day of real data on an empty chart,
or it shows a labelled synthetic history alongside the real data.

We do the second, and we label it. Every row written here carries
source_class = 'SIMULATED'. There is no flag to turn that off. The dashboard
renders simulated series differently and says so in the legend.

THE MODEL (state this out loud in the demo; it is documented in METHODOLOGY.md)
------------------------------------------------------------------------------
    fare = base_route_fare
           x window_multiplier(w)      advance-purchase curve
           x weekday_factor(dow)       Friday/Sunday peaks
           x seasonality(t)            anchored on the REAL MoSPI airfare index
           x lognormal_noise           dispersion within a cell
           x festival_surge(t)         one deliberate real-world shock

Seasonality is not invented: it interpolates MoSPI's published
"Air fare [normal]: economy class [adult]" index (Base 2012=100, Annex-V),
extracted by scripts/extract_mospi_airfare.py. The shape of the synthetic
history therefore follows an actual official airfare series.

Base route fares are ORDER-OF-MAGNITUDE PLACEHOLDERS chosen to be plausible for
Indian domestic economy one-way fares. They are not measurements and must never
be presented as such.
"""
from __future__ import annotations

import json
import math
import random
from datetime import date, timedelta

from apix.config import DATA_DIR, departure_date, load_basket
from apix.collect.base import RawResponse, SourceAdapter
from apix.vocab import ObsStatus, SourceClass

# Deterministic. The same seed regenerates the identical history, so a demo is
# reproducible and a test can assert on exact values.
SEED = 26056

# Placeholder base fares in INR: typical cheapest economy one-way, T+21-ish.
# Longer/denser trunk routes priced higher. NOT measured values.
BASE_FARE = {
    "DEL-BOM": 5200.0,
    "DEL-BLR": 5900.0,
    "BOM-BLR": 4300.0,
    "DEL-CCU": 5600.0,
    "BLR-HYD": 3400.0,
    "MAA-DEL": 6100.0,
}

# Advance-purchase curve. T+1 is dramatically dearer; the curve flattens out
# past about three weeks. This is the shape APIx exists to expose -- no official
# index anywhere publishes it.
WINDOW_MULTIPLIER = {1: 2.35, 7: 1.42, 14: 1.15, 21: 1.00, 45: 0.92}

# Monday=0 ... Sunday=6
WEEKDAY_FACTOR = [0.96, 0.94, 0.95, 1.00, 1.12, 1.02, 1.10]

# Cell pathology rates, so the quality machinery has something to catch.
P_SOLD_OUT = 0.030
P_PARSE_FAIL = 0.015
P_FETCH_FAIL = 0.010
BLOCKED_RUN_DAYS = 2      # one deliberate multi-day outage
FLIGHTS_PER_CELL = (4, 9)  # quotes returned per search

CARRIERS = ["6E", "AI", "SG", "QP", "IX", "UK"]


def _load_mospi_seasonality() -> dict:
    p = DATA_DIR / "mospi_airfare_index.json"
    if not p.exists():
        return {}
    payload = json.loads(p.read_text(encoding="utf-8"))
    return {o["period"]: o["index"] for o in payload.get("observations", [])}


class ReplayAdapter(SourceAdapter):
    source_id = "replay"
    source_class = SourceClass.SIMULATED

    def __init__(self, anchor_date: date | None = None, seed: int = SEED):
        self.basket = load_basket()
        self.seed = seed
        self.anchor = anchor_date or date.today()
        self.mospi = _load_mospi_seasonality()
        self._mospi_mean = (
            sum(self.mospi.values()) / len(self.mospi) if self.mospi else 1.0
        )
        # A single deliberate outage window, so BLOCKED appears in the series.
        self.blocked_from = self.anchor - timedelta(days=23)
        self.blocked_to = self.blocked_from + timedelta(days=BLOCKED_RUN_DAYS - 1)
        # A festival surge, so a genuine outlier appears and the median resists.
        self.surge_from = self.anchor - timedelta(days=11)
        self.surge_to = self.surge_from + timedelta(days=2)

    # -- model components ---------------------------------------------------
    def _seasonality(self, dep: date) -> float:
        """Scale by the real MoSPI airfare index for the nearest month held.

        Falls back to a mild annual sinusoid when the MoSPI extract is absent,
        so the module never silently depends on a file that may not be there.
        """
        if not self.mospi:
            return 1.0 + 0.05 * math.sin(2 * math.pi * dep.timetuple().tm_yday / 365.0)
        key = f"{dep.year}-{dep.month:02d}"
        if key in self.mospi:
            val = self.mospi[key]
        else:
            # Nearest month available in the extract, by calendar distance.
            target = dep.year * 12 + dep.month
            best = min(
                self.mospi,
                key=lambda k: abs(
                    (int(k[:4]) * 12 + int(k[5:7])) - target
                ),
            )
            val = self.mospi[best]
        return val / self._mospi_mean

    def _rng(self, route: str, window: int, obs: date) -> random.Random:
        """Per-cell deterministic RNG: regenerating any single cell is stable
        regardless of the order cells are generated in."""
        return random.Random(f"{self.seed}|{route}|{window}|{obs.isoformat()}")

    def _cell_status(self, rng: random.Random, obs: date) -> ObsStatus:
        if self.blocked_from <= obs <= self.blocked_to:
            return ObsStatus.BLOCKED
        roll = rng.random()
        if roll < P_SOLD_OUT:
            return ObsStatus.SOLD_OUT
        if roll < P_SOLD_OUT + P_PARSE_FAIL:
            return ObsStatus.PARSE_FAIL
        if roll < P_SOLD_OUT + P_PARSE_FAIL + P_FETCH_FAIL:
            return ObsStatus.FETCH_FAIL
        return ObsStatus.OK

    def _quotes(self, route: str, window: int, obs: date, dep: date,
                rng: random.Random) -> list[dict]:
        base = BASE_FARE.get(route, 5000.0)
        mult = WINDOW_MULTIPLIER.get(window, 1.0)
        dow = WEEKDAY_FACTOR[dep.weekday()]
        seas = self._seasonality(dep)

        surge = 1.0
        if self.surge_from <= obs <= self.surge_to:
            surge = 1.55  # festival demand: real, and the median should resist it

        centre = base * mult * dow * seas * surge
        n = rng.randint(*FLIGHTS_PER_CELL)
        out = []
        for i in range(n):
            # Lognormal dispersion: fare distributions are right-skewed, and a
            # few genuine last-minute fares run several times the typical one.
            noise = math.exp(rng.gauss(0.0, 0.16))
            total = round(centre * noise, 0)
            # Indian domestic: taxes and fees are a meaningful slice of total.
            taxes = round(total * rng.uniform(0.10, 0.14), 0)
            fees = round(total * rng.uniform(0.02, 0.04), 0)
            out.append(
                {
                    "carrier": rng.choice(CARRIERS),
                    "flight_no": f"{rng.randint(100, 9999)}",
                    "departure_time": f"{rng.randint(0, 23):02d}:{rng.choice(['00','15','30','45'])}",
                    "stops": 0 if rng.random() < 0.82 else 1,
                    "base_fare": round(total - taxes - fees, 0),
                    "taxes": taxes,
                    "fees": fees,
                    "total_fare": total,
                    "currency": "INR",
                }
            )
        return out

    # -- adapter interface --------------------------------------------------
    def search(
        self, route_code: str, window_days: int, observation_date: date
    ) -> RawResponse:
        dep = departure_date(observation_date, window_days)
        rng = self._rng(route_code, window_days, observation_date)
        status = self._cell_status(rng, observation_date)

        common = dict(
            source_id=self.source_id,
            source_class=self.source_class,
            observation_date=observation_date,
            route_code=route_code,
            window_days=window_days,
            departure_date=dep,
            request_url=f"replay://{route_code}/T+{window_days}/{observation_date}",
            user_agent="APIx-Replay/0.1 (SIMULATED)",
        )

        if status is ObsStatus.BLOCKED:
            return RawResponse(
                fetch_status=status, http_status=403,
                error_detail="simulated bot wall (scheduled outage in replay model)",
                **common,
            )
        if status is ObsStatus.FETCH_FAIL:
            return RawResponse(
                fetch_status=status, http_status=504,
                error_detail="simulated upstream timeout", **common,
            )
        if status is ObsStatus.PARSE_FAIL:
            # Fetched fine, but the shape changed. Bronze keeps the payload so
            # history can be re-parsed once the adapter is fixed.
            return RawResponse(
                fetch_status=status, http_status=200,
                payload=json.dumps({"unexpected": "layout changed", "results": None}),
                error_detail="simulated markup change", **common,
            )
        if status is ObsStatus.SOLD_OUT:
            return RawResponse(
                fetch_status=status, http_status=200,
                payload=json.dumps({"route": route_code, "quotes": []}), **common,
            )

        quotes = self._quotes(route_code, window_days, observation_date, dep, rng)
        payload = json.dumps(
            {
                "_disclaimer": "SIMULATED DATA generated by apix.collect.replay",
                "route": route_code,
                "window_days": window_days,
                "departure_date": dep.isoformat(),
                "quotes": quotes,
            },
            indent=None,
        )
        return RawResponse(
            fetch_status=ObsStatus.OK, http_status=200, payload=payload, **common
        )
