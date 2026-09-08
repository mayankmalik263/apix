"""Aggregations the dashboard and the API both read.

Covers the outputs the problem statement names directly: daily/weekly/monthly
frequencies, lead-time elasticity, sector heatmaps, and the base/tax/fee split.
Pure reads — nothing here writes.
"""
from __future__ import annotations

import sqlite3
import statistics
from collections import Counter, defaultdict


def _rows(conn, sql, *a):
    try:
        return [dict(r) for r in conn.execute(sql, a).fetchall()]
    except sqlite3.OperationalError:
        return []


def _one(conn, sql, *a, default=0):
    try:
        v = conn.execute(sql, a).fetchone()
        return v[0] if v and v[0] is not None else default
    except sqlite3.OperationalError:
        return default


def effective_class(conn, requested: str) -> str:
    """LIVE if a real day has been indexed, otherwise the labelled history.

    Returned to the caller so the UI can say which one it is showing. Swapping
    them silently is the one substitution this project cannot make.
    """
    sc = requested.upper()
    if sc != "LIVE":
        return sc
    have = _one(conn, "SELECT COUNT(*) FROM gold_apix_daily WHERE source_class='LIVE'")
    return "LIVE" if have else "SIMULATED"


# ---------------------------------------------------------------------------
# frequencies — the brief asks for daily, weekly and monthly
# ---------------------------------------------------------------------------
def series(conn, source_class: str, freq: str = "daily") -> list[dict]:
    """The published series at the requested frequency.

    Weekly and monthly are means of the daily index over the period, carrying
    the period's mean coverage and its worst confidence grade. Taking the last
    day of the period instead would make the figure depend on which weekday the
    month happened to end on.
    """
    daily = _rows(conn, """
        SELECT observation_date, apix, change_pct, coverage, n_expected,
               n_observed, confidence
        FROM gold_apix_daily
        WHERE source_class = ? AND apix IS NOT NULL
        ORDER BY observation_date""", source_class)

    if freq == "daily" or not daily:
        return daily

    key = (lambda d: d[:7]) if freq == "monthly" else _isoweek
    buckets: dict[str, list[dict]] = defaultdict(list)
    for r in daily:
        buckets[key(r["observation_date"])].append(r)

    worst = {"A": 0, "B": 1, "C": 2}
    out = []
    for period in sorted(buckets):
        rs = buckets[period]
        grade = max((r["confidence"] for r in rs), key=lambda g: worst.get(g, 3))
        out.append({
            "observation_date": period,
            "period_start": rs[0]["observation_date"],
            "period_end": rs[-1]["observation_date"],
            "apix": round(statistics.fmean(r["apix"] for r in rs), 4),
            "coverage": round(statistics.fmean(r["coverage"] for r in rs), 4),
            "confidence": grade,
            "n_days": len(rs),
        })
    for i in range(1, len(out)):
        prev = out[i - 1]["apix"]
        out[i]["change_pct"] = round(100 * (out[i]["apix"] - prev) / prev, 4) if prev else None
    if out:
        out[0]["change_pct"] = None
    return out


def _isoweek(d: str) -> str:
    from datetime import date
    y, w, _ = date.fromisoformat(d).isocalendar()
    return f"{y}-W{w:02d}"


# ---------------------------------------------------------------------------
# lead-time elasticity — named in the brief
# ---------------------------------------------------------------------------
def lead_time(conn, source_class: str, observation_date: str | None = None) -> dict:
    """Median fare by booking window, and the change between adjacent windows.

    Elasticity here is the percentage change in fare per day of extra lead
    time between one window and the next — a slope, not a regression
    coefficient, and labelled as such so it is not mistaken for one.
    """
    if observation_date is None:
        observation_date = _one(conn,
            "SELECT MAX(observation_date) FROM gold_cell_median WHERE source_class=?",
            source_class, default=None)
    if not observation_date:
        return {"available": False, "reason": "no cell medians computed yet"}

    cells = _rows(conn, """
        SELECT route_code, window_days, median_fare, n_used
        FROM gold_cell_median
        WHERE source_class = ? AND observation_date = ? AND median_fare IS NOT NULL
        ORDER BY route_code, window_days""", source_class, observation_date)
    if not cells:
        return {"available": False, "reason": "no priced cells on that day"}

    by_window = defaultdict(list)
    for c in cells:
        by_window[c["window_days"]].append(c["median_fare"])

    windows = sorted(by_window)
    curve = []
    for i, w in enumerate(windows):
        fares = by_window[w]
        row = {"window_days": w, "median": round(statistics.median(fares), 2),
               "n_routes": len(fares)}
        if i:
            prev_w, prev_f = windows[i - 1], curve[i - 1]["median"]
            pct = 100 * (row["median"] - prev_f) / prev_f
            row["change_pct"] = round(pct, 2)
            row["pct_per_day"] = round(pct / (w - prev_w), 3)
        curve.append(row)

    cheapest = min(curve, key=lambda r: r["median"])
    dearest = max(curve, key=lambda r: r["median"])
    return {
        "available": True,
        "observation_date": observation_date,
        "curve": curve,
        "by_route": _lead_time_by_route(cells),
        "cheapest_window": cheapest["window_days"],
        "cheapest_median": cheapest["median"],
        "dearest_window": dearest["window_days"],
        "dearest_median": dearest["median"],
        "spread_pct": round(100 * (dearest["median"] - cheapest["median"])
                            / cheapest["median"], 1),
        # Booking earliest is not automatically cheapest. Whether the curve
        # turns back up at long lead times is exactly what no official index
        # publishes, so it is reported rather than assumed.
        "u_shaped": curve[-1]["median"] > cheapest["median"] * 1.02,
    }


def _lead_time_by_route(cells: list[dict]) -> list[dict]:
    by_route = defaultdict(dict)
    for c in cells:
        by_route[c["route_code"]][c["window_days"]] = c["median_fare"]
    out = []
    for route, m in sorted(by_route.items()):
        if not m:
            continue
        cheap_w = min(m, key=lambda w: m[w])
        out.append({
            "route_code": route,
            "points": [{"window_days": w, "median": m[w]} for w in sorted(m)],
            "cheapest_window": cheap_w,
            "cheapest_median": m[cheap_w],
            "max_median": max(m.values()),
            "spread_pct": round(100 * (max(m.values()) - m[cheap_w]) / m[cheap_w], 1),
        })
    return out


# ---------------------------------------------------------------------------
# fare composition — the brief asks for base fare separated from taxes and fees
# ---------------------------------------------------------------------------
def composition(conn, source_class: str, observation_date: str | None = None) -> dict:
    if observation_date is None:
        observation_date = _one(conn,
            "SELECT MAX(observation_date) FROM silver_fare_observation WHERE source_class=?",
            source_class, default=None)
    if not observation_date:
        return {"available": False, "reason": "nothing loaded yet"}

    rows = _rows(conn, """
        SELECT route_code,
               ROUND(AVG(base_fare)) base_fare,
               ROUND(AVG(taxes))     taxes,
               ROUND(AVG(fees))      fees,
               ROUND(AVG(total_fare)) total,
               COUNT(*) n
        FROM silver_fare_observation
        WHERE source_class = ? AND observation_date = ? AND status = 'OK'
          AND base_fare IS NOT NULL
        GROUP BY route_code ORDER BY route_code""", source_class, observation_date)
    if not rows:
        return {"available": False,
                "reason": "this source does not break the fare down"}

    tot = _rows(conn, """
        SELECT ROUND(AVG(base_fare)) base_fare, ROUND(AVG(taxes)) taxes,
               ROUND(AVG(fees)) fees, ROUND(AVG(total_fare)) total, COUNT(*) n
        FROM silver_fare_observation
        WHERE source_class = ? AND observation_date = ? AND status = 'OK'
          AND base_fare IS NOT NULL""", source_class, observation_date)[0]

    t = tot["total"] or 1
    return {
        "available": True, "observation_date": observation_date,
        "by_route": rows, "overall": tot,
        "tax_share_pct": round(100 * ((tot["taxes"] or 0) + (tot["fees"] or 0)) / t, 1),
    }


# ---------------------------------------------------------------------------
# lineage — a published number back to the bytes it came from
# ---------------------------------------------------------------------------
def lineage(conn, observation_date: str, route: str, window: int,
            source_class: str) -> dict:
    route = route.upper()
    cell = _rows(conn, """
        SELECT * FROM gold_cell_median
        WHERE observation_date=? AND route_code=? AND window_days=? AND source_class=?""",
        observation_date, route, window, source_class)

    fares = _rows(conn, """
        SELECT source_id, carrier, flight_no, base_fare, taxes, fees, total_fare,
               status, is_outlier, outlier_score, fare_ref
        FROM silver_fare_observation
        WHERE observation_date=? AND route_code=? AND window_days=? AND source_class=?
        ORDER BY total_fare""", observation_date, route, window, source_class)

    raw = []
    try:
        from datetime import date as _d
        from apix.collect import bronze
        for rec in bronze.read_day(_d.fromisoformat(observation_date)):
            # source_class matters as much as route and window. Without it a
            # LIVE cell can be shown a SIMULATED payload as its origin, which
            # is the one mistake this whole feature exists to make impossible.
            if (rec["route_code"] == route
                    and int(rec["window_days"]) == window
                    and rec["source_class"] == source_class):
                raw.append({
                    "source_id": rec["source_id"],
                    "source_class": rec["source_class"],
                    "fetch_status": rec["fetch_status"],
                    "http_status": rec.get("http_status"),
                    "request_url": rec.get("request_url"),
                    "payload_bytes": len(rec["payload"]) if rec.get("payload") else 0,
                    "payload_sha256": rec.get("payload_sha256"),
                    "fetched_at_utc": rec.get("fetched_at_utc"),
                })
    except Exception:
        pass

    # A cell can hold several Bronze attempts: a compliance refusal, a timeout,
    # then the fetch that actually worked. Order them so the record the parse
    # came from is first, otherwise the lineage shows a zero-byte refusal as the
    # origin of a median built from 142 real fares.
    raw.sort(key=lambda r: (r["payload_bytes"] > 0, r.get("fetched_at_utc") or ""),
             reverse=True)

    return {
        "cell": {"observation_date": observation_date, "route_code": route,
                 "window_days": window, "source_class": source_class},
        "gold": cell[0] if cell else None,
        "silver": fares,
        "silver_count": len(fares),
        # Matches the engine: the median is taken over every OK fare. Flagged
        # rows are included, which is the whole point of flagging rather than
        # deleting. Counting them out here made the drawer contradict the
        # number it was explaining.
        "used_in_median": sum(1 for f in fares if f["status"] == "OK"),
        "attempts": len(raw),
        "flagged": sum(1 for f in fares if f["is_outlier"]),
        "bronze": raw,
    }


# ---------------------------------------------------------------------------
# everything the dashboard opens with
# ---------------------------------------------------------------------------
def overview(conn, requested_class: str = "LIVE", freq: str = "daily") -> dict:
    sc = effective_class(conn, requested_class)
    s = series(conn, sc, freq)
    daily = series(conn, sc, "daily")
    latest = s[-1] if s else None
    day = daily[-1]["observation_date"] if daily else None

    cells = _rows(conn, """
        SELECT route_code, window_days, median_fare, n_used, n_outliers_flagged,
               status, price_relative
        FROM gold_cell_median WHERE source_class=? AND observation_date=?
        ORDER BY route_code, window_days""", sc, day) if day else []

    routes = _rows(conn, """
        SELECT route_code, route_index, n_windows_used, n_observations, coverage
        FROM gold_route_index_daily WHERE source_class=? AND observation_date=?
        ORDER BY route_code""", sc, day) if day else []

    carriers = _rows(conn, """
        SELECT carrier, COUNT(*) n, ROUND(AVG(total_fare)) avg_fare,
               MIN(total_fare) min_fare, MAX(total_fare) max_fare
        FROM silver_fare_observation
        WHERE source_class=? AND status='OK' AND carrier IS NOT NULL
              AND observation_date=?
        GROUP BY carrier ORDER BY n DESC LIMIT 12""", sc, day) if day else []

    fares = [r["total_fare"] for r in _rows(conn, """
        SELECT total_fare FROM silver_fare_observation
        WHERE source_class=? AND status='OK' AND observation_date=?
              AND total_fare IS NOT NULL""", sc, day)] if day else []

    hist, spread = [], {}
    if fares:
        f = sorted(fares)
        lo, hi, bins = f[0], f[-1], 26
        width = max(1.0, (hi - lo) / bins)
        counts = Counter(min(bins - 1, int((x - lo) / width)) for x in f)
        hist = [{"from": round(lo + i * width), "to": round(lo + (i + 1) * width),
                 "count": counts.get(i, 0)} for i in range(bins)]
        spread = {"n": len(f), "min": f[0], "p25": f[len(f) // 4],
                  "median": statistics.median(f), "p75": f[3 * len(f) // 4],
                  "max": f[-1], "mean": round(statistics.fmean(f), 2)}

    status_mix = _rows(conn, """
        SELECT status, status_class, COUNT(*) n FROM silver_fare_observation
        WHERE source_class=? GROUP BY status, status_class ORDER BY n DESC""", sc)

    outliers = _rows(conn, """
        SELECT route_code, window_days, carrier, total_fare, outlier_score
        FROM silver_fare_observation
        WHERE source_class=? AND is_outlier=1 AND observation_date=?
        ORDER BY ABS(outlier_score) DESC LIMIT 40""", sc, day) if day else []

    # The generated history is always returned alongside the measured series
    # rather than instead of it: with one measured day the chart would
    # otherwise be a single dot with no context behind it.
    other = "SIMULATED" if sc == "LIVE" else "LIVE"
    context = series(conn, other, freq)

    return {
        "source_class": sc,
        "context_class": other,
        "context_series": context,
        "requested_source_class": requested_class.upper(),
        "using_generated_history": sc != requested_class.upper(),
        "frequency": freq,
        "latest": latest,
        "series": s,
        "daily_series": daily,
        "observation_date": day,
        "cells": cells,
        "routes": routes,
        "carriers": carriers,
        "histogram": hist,
        "spread": spread,
        "status_mix": status_mix,
        "outliers": outliers,
        "lead_time": lead_time(conn, sc, day),
        "composition": composition(conn, sc, day),
        "counts": {
            "silver_rows": _one(conn, "SELECT COUNT(*) FROM silver_fare_observation"),
            "flagged": _one(conn, "SELECT COUNT(*) FROM silver_fare_observation WHERE is_outlier=1"),
            "published_days": _one(conn, "SELECT COUNT(*) FROM gold_apix_daily"),
            "live_days": _one(conn, "SELECT COUNT(*) FROM gold_apix_daily WHERE source_class='LIVE'"),
        },
    }
