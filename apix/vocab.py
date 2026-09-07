"""
The controlled vocabulary. This is a CONTRACT, not a database detail.

Owned by the collection layer, consumed by the database and the index engine.
The schema stores these values and rejects anything else.

The rule this file exists to enforce:

    A missing price and a broken collector are different facts.

Collapsing both into NULL is how a statistical series starts lying. Every
observation APIx records carries a reason, and the reason determines whether
the gap counts against us, against the market, or against nobody.
"""
from __future__ import annotations

import enum


class ObsStatus(str, enum.Enum):
    OK = "OK"                                # MARKET - fare captured, parsed
    SOLD_OUT = "SOLD_OUT"                    # MARKET - served, no inventory
    NO_SERVICE = "NO_SERVICE"                # MARKET - no flight on this pair
    SOURCE_DISALLOWED = "SOURCE_DISALLOWED"  # POLICY - registry blocked it
    FETCH_FAIL = "FETCH_FAIL"                # SYSTEM - timeout, 5xx, network
    BLOCKED = "BLOCKED"                      # SYSTEM - bot wall, never bypassed
    PARSE_FAIL = "PARSE_FAIL"                # SYSTEM - fetched, shape changed


# Who the gap belongs to. Drives how the index treats it.
#   MARKET  the market said something; that IS the observation
#   POLICY  we chose not to collect; a reportable coverage gap, never hidden
#   SYSTEM  we failed; lowers coverage and downgrades confidence
STATUS_CLASS: dict[ObsStatus, str] = {
    ObsStatus.OK: "MARKET",
    ObsStatus.SOLD_OUT: "MARKET",
    ObsStatus.NO_SERVICE: "MARKET",
    ObsStatus.SOURCE_DISALLOWED: "POLICY",
    ObsStatus.FETCH_FAIL: "SYSTEM",
    ObsStatus.BLOCKED: "SYSTEM",
    ObsStatus.PARSE_FAIL: "SYSTEM",
}

# Counts as "we successfully observed the market" for coverage.
COVERAGE_NUMERATOR = {ObsStatus.OK.value, ObsStatus.SOLD_OUT.value}

# No flight exists, so there was never anything to observe. These leave the
# denominator rather than being counted as a failure to collect.
EXCLUDED_FROM_EXPECTED = {ObsStatus.NO_SERVICE.value}


class SourceClass(str, enum.Enum):
    LIVE = "LIVE"            # genuinely fetched from a portal
    SIMULATED = "SIMULATED"  # replay-generated, from a documented model
    MANUAL = "MANUAL"        # human ground-truth panel


def status_class(status: str | ObsStatus) -> str:
    return STATUS_CLASS[ObsStatus(status)]
