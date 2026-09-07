"""
The compliance gate.

This is not a document. It is a runtime check the collector cannot route
around. `assert_permitted()` raises BEFORE any network call is made, and it
reads a verdict produced by an actual robots.txt fetch performed today -- not a
verdict typed into a YAML file by a human.

STORAGE
-------
Verdicts are written to compliance/verdicts/<date>.json and the robots.txt
bodies to compliance/evidence/. Deliberately files, not a database: the
compliance trail must survive the database being dropped and rebuilt, and it
lets the collection layer run before the database layer exists.

The database layer (Bharat) loads compliance/verdicts/*.json into the
source_registry table. Read-only, one direction, no shared code.

DESIGN POSITION
---------------
SIH26056 asks for CAPTCHA handling and IP rotation AND for robots.txt + ToS
compliance. Those cannot both hold. APIx answers with a permission-tiered
acquisition architecture, and reports the sources that refuse collection as a
finding about market observability rather than an obstacle to be defeated.
"""
from __future__ import annotations

import hashlib
import json
import urllib.robotparser
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import httpx

from apix.config import COMPLIANCE_DIR, EVIDENCE_DIR, load_registry

PERMITTED = "PERMITTED"
DISALLOWED = "DISALLOWED"
BLOCKED = "BLOCKED"
UNKNOWN = "UNKNOWN"

FETCH_TIMEOUT = 15.0
VERDICT_DIR = COMPLIANCE_DIR / "verdicts"


class ComplianceError(RuntimeError):
    """Raised when collection is attempted against an uncleared source."""


@dataclass
class CheckResult:
    source_id: str
    source_name: str
    kind: str
    robots_url: str
    fare_path: str
    verdict: str
    reason: str
    checked_on: str
    http_status: int | None = None
    robots_sha256: str | None = None
    path_allowed: bool | None = None
    crawl_delay: float | None = None
    evidence_file: str | None = None


def _user_agent() -> str:
    return load_registry()["etiquette"]["user_agent"]


def _verdict_file(on: date) -> Path:
    return VERDICT_DIR / f"{on.isoformat()}.json"


def _evidence_path(source_id: str, on: date) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    return EVIDENCE_DIR / f"{on.isoformat()}_{source_id}_robots.txt"


# ---------------------------------------------------------------------------
# Checking
# ---------------------------------------------------------------------------
def check_source(src: dict, on: date | None = None) -> CheckResult:
    """Fetch one source's robots.txt, hash it as evidence, and decide.

    A fetch failure is deliberately NOT treated as permission. If we cannot
    read the rules, we do not collect.
    """
    on = on or date.today()
    base = src["base_url"].rstrip("/")
    robots_url = f"{base}/robots.txt"
    fare_path = src.get("fare_path", "/")
    target = urljoin(base + "/", fare_path.lstrip("/"))
    ua = _user_agent()

    common = dict(
        source_id=src["id"],
        source_name=src["name"],
        kind=src.get("kind", "unknown"),
        robots_url=robots_url,
        fare_path=fare_path,
        checked_on=on.isoformat(),
    )

    try:
        resp = httpx.get(
            robots_url,
            headers={"User-Agent": ua},
            timeout=FETCH_TIMEOUT,
            follow_redirects=True,
        )
    except Exception as exc:  # network error, DNS, TLS, timeout
        return CheckResult(
            verdict=BLOCKED,
            reason=(
                f"could not fetch robots.txt: {type(exc).__name__}. "
                "NOT proof of a bot wall -- may be network. Re-run to confirm."
            ),
            **common,
        )

    body = resp.text or ""
    sha = hashlib.sha256(body.encode("utf-8", "replace")).hexdigest()

    evidence = _evidence_path(src["id"], on)
    evidence.write_text(
        f"# APIx compliance evidence\n"
        f"# source_id: {src['id']}\n"
        f"# url: {robots_url}\n"
        f"# http_status: {resp.status_code}\n"
        f"# fetched_at_utc: {datetime.now(timezone.utc).isoformat()}\n"
        f"# sha256: {sha}\n"
        f"# --------------- verbatim robots.txt below ---------------\n" + body,
        encoding="utf-8",
    )
    common["robots_sha256"] = sha
    common["http_status"] = resp.status_code
    common["evidence_file"] = str(evidence.relative_to(COMPLIANCE_DIR.parent))

    if resp.status_code == 404:
        # No robots.txt published. Conventionally permissive, but we still
        # require a human ToS review before this becomes PERMITTED, so it stays
        # UNKNOWN and the gate keeps refusing.
        return CheckResult(
            verdict=UNKNOWN,
            reason="no robots.txt (404); ToS review required before use",
            **common,
        )

    if resp.status_code != 200:
        return CheckResult(
            verdict=BLOCKED,
            reason=f"robots.txt returned HTTP {resp.status_code}",
            **common,
        )

    parser = urllib.robotparser.RobotFileParser()
    parser.parse(body.splitlines())
    allowed = parser.can_fetch(ua, target)
    try:
        delay = parser.crawl_delay(ua)
    except Exception:
        delay = None

    return CheckResult(
        verdict=PERMITTED if allowed else DISALLOWED,
        reason=(
            f"robots.txt allows {fare_path}" if allowed
            else f"robots.txt disallows {fare_path}"
        ),
        path_allowed=allowed,
        crawl_delay=float(delay) if delay is not None else None,
        **common,
    )


def run_checks(on: date | None = None, only: list[str] | None = None) -> list[CheckResult]:
    """Check every registered source and persist the verdict ledger."""
    on = on or date.today()
    sources = load_registry()["sources"]
    if only:
        wanted = set(only)
        sources = [s for s in sources if s["id"] in wanted]

    results = [check_source(src, on=on) for src in sources]

    VERDICT_DIR.mkdir(parents=True, exist_ok=True)
    _verdict_file(on).write_text(
        json.dumps(
            {
                "checked_on": on.isoformat(),
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "user_agent": _user_agent(),
                "results": [asdict(r) for r in results],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return results


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------
def load_verdicts(on: date | None = None) -> dict[str, dict]:
    on = on or date.today()
    p = _verdict_file(on)
    if not p.exists():
        return {}
    payload = json.loads(p.read_text(encoding="utf-8"))
    return {r["source_id"]: r for r in payload.get("results", [])}


def verdict_for(source_id: str, on: date | None = None) -> tuple[str, str]:
    """Today's stored verdict for a source. Absence is not permission."""
    row = load_verdicts(on).get(source_id)
    if row is None:
        return UNKNOWN, "no compliance check recorded for today"
    return row["verdict"], row.get("reason", "")


def assert_permitted(source_id: str, on: date | None = None) -> None:
    """Raise unless this source was cleared PERMITTED by a check dated today.

    Called before the network layer is touched, so an uncleared source cannot
    be reached even by mistake.
    """
    verdict, reason = verdict_for(source_id, on=on)
    if verdict != PERMITTED:
        raise ComplianceError(
            f"refusing to collect from '{source_id}': verdict={verdict} ({reason})"
        )


def permitted_sources(on: date | None = None) -> list[str]:
    return [
        sid for sid, r in load_verdicts(on).items() if r["verdict"] == PERMITTED
    ]


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def report(on: date | None = None) -> list[dict]:
    """The compliance table, ready to print or put on a slide."""
    on = on or date.today()
    stored = load_verdicts(on)
    rows = []
    for src in load_registry()["sources"]:
        r = stored.get(src["id"])
        sha = r.get("robots_sha256") if r else None
        rows.append(
            {
                "source_id": src["id"],
                "name": src["name"],
                "kind": src["kind"],
                "checked_on": r["checked_on"] if r else "-",
                "http": r.get("http_status") if r else None,
                "verdict": r["verdict"] if r else UNKNOWN,
                "reason": r.get("reason", "") if r else "not checked",
                "sha256": (sha[:12] + "...") if sha else "-",
                "crawl_delay": r.get("crawl_delay") if r else None,
                "evidence_file": r.get("evidence_file") if r else None,
            }
        )
    return rows
