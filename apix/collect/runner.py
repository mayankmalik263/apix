"""
Collection runner: adapter -> Bronze.

Two rules are enforced here rather than trusted to callers.

1. NO REQUEST WITHOUT CLEARANCE. For a LIVE source the compliance gate is
   checked before the adapter is called at all, so the network layer is never
   reached for a source we have not cleared today. When the gate refuses, the
   refusal is still written to Bronze as SOURCE_DISALLOWED -- a coverage gap
   we chose, recorded as evidence rather than hidden.

2. EVERY OUTCOME IS WRITTEN. A BLOCKED row is data. A timeout is data. An
   exception that escapes this module is a permanently lost observation,
   because tomorrow cannot re-collect today.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, timedelta

from apix.collect import bronze
from apix.collect.base import RawResponse, SourceAdapter
from apix.collect.compliance import ComplianceError, assert_permitted
from apix.config import departure_date, load_basket, load_registry
from apix.vocab import ObsStatus, SourceClass


@dataclass
class CollectSummary:
    observation_date: date
    source_id: str
    written: int = 0
    skipped_existing: int = 0
    by_status: dict = field(default_factory=dict)
    gate_refused: str | None = None

    @property
    def ok(self) -> int:
        return self.by_status.get(ObsStatus.OK.value, 0)

    def line(self) -> str:
        head = f"{self.observation_date}  {self.source_id:<14}"
        if self.gate_refused:
            return f"{head}REFUSED   {self.gate_refused}"
        counts = "  ".join(f"{k}={v}" for k, v in sorted(self.by_status.items()))
        skip = f"  (skipped {self.skipped_existing} already collected)" if self.skipped_existing else ""
        return f"{head}wrote {self.written:>3}   {counts}{skip}"


def _refusal_rows(adapter: SourceAdapter, obs_date: date, reason: str) -> list[RawResponse]:
    """The gate said no. Record all 30 cells as SOURCE_DISALLOWED so coverage
    reporting can show exactly what we chose not to collect, and why."""
    basket = load_basket()
    return [
        RawResponse(
            source_id=adapter.source_id,
            source_class=adapter.source_class,
            observation_date=obs_date,
            route_code=route.code,
            window_days=w,
            departure_date=departure_date(obs_date, w),
            fetch_status=ObsStatus.SOURCE_DISALLOWED,
            error_detail=reason,
        )
        for route in basket.routes
        for w in basket.windows
    ]


def collect_day(
    adapter: SourceAdapter,
    observation_date: date,
    *,
    enforce_gate: bool = True,
    resume: bool = True,
    throttle: bool | None = None,
    only_routes: list[str] | None = None,
    only_windows: list[int] | None = None,
) -> CollectSummary:
    """Collect the day's cells for one adapter. Subset flags exist so a demo
    can run one live cell in seconds rather than the full grid."""
    basket = load_basket()
    summary = CollectSummary(observation_date=observation_date, source_id=adapter.source_id)

    is_live = adapter.source_class is SourceClass.LIVE

    # ---- the gate, before any network call ----
    if enforce_gate and is_live:
        try:
            assert_permitted(adapter.source_id, on=observation_date)
        except ComplianceError as exc:
            rows = _refusal_rows(adapter, observation_date, str(exc))
            bronze.append_many(rows)
            summary.written = len(rows)
            summary.by_status = {ObsStatus.SOURCE_DISALLOWED.value: len(rows)}
            summary.gate_refused = str(exc)
            return summary

    # Politeness budget. Only applied to live sources -- throttling a local
    # generator would just make the demo slow for no reason.
    if throttle is None:
        throttle = is_live
    delay = float(load_registry().get("etiquette", {}).get("min_seconds_between_requests", 0) or 0)

    already = bronze.existing_cells(observation_date, adapter.source_id) if resume else set()

    routes = [r for r in basket.routes
              if not only_routes or r.code in set(only_routes)]
    windows = [w for w in basket.windows
               if not only_windows or w in set(only_windows)]

    for route in routes:
        for w in windows:
            if (route.code, w) in already:
                summary.skipped_existing += 1
                continue
            try:
                resp = adapter.search(route.code, w, observation_date)
            except Exception as exc:
                # An adapter that raises is a bug, but losing the cell is worse
                # than recording the bug. Write it as a system failure.
                resp = RawResponse(
                    source_id=adapter.source_id,
                    source_class=adapter.source_class,
                    observation_date=observation_date,
                    route_code=route.code,
                    window_days=w,
                    departure_date=departure_date(observation_date, w),
                    fetch_status=ObsStatus.FETCH_FAIL,
                    error_detail=f"adapter raised {type(exc).__name__}: {exc}",
                )
            bronze.append(resp)
            summary.written += 1
            k = resp.fetch_status.value
            summary.by_status[k] = summary.by_status.get(k, 0) + 1

            if throttle and delay:
                time.sleep(delay)

    return summary


def collect_range(
    adapter: SourceAdapter, start: date, end: date, **kwargs
) -> list[CollectSummary]:
    out, d = [], start
    while d <= end:
        out.append(collect_day(adapter, d, **kwargs))
        d += timedelta(days=1)
    return out
