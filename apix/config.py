"""Configuration loading. Basket and compliance registry are data, not code."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
COMPLIANCE_DIR = ROOT / "compliance"
DATA_DIR = ROOT / "data"
EVIDENCE_DIR = COMPLIANCE_DIR / "evidence"

# Postgres is the stated production target; SQLite is what actually runs.
#
# Be accurate about what that migration costs. There is no ORM in this project:
# eighteen modules use the sqlite3 driver directly, so moving to Postgres means
# swapping the driver and the connection handling in those modules, not
# flipping one environment variable. db/schema.postgres.sql is the schema half
# of the job and is real; the application half is not written.
#
# APIX_DB_URL is read and returned below, and nothing consumes it yet. It is
# kept because the URL form is what a Postgres deployment would configure, and
# removing it would lose the only declared place that setting belongs.
DEFAULT_DB_URL = f"sqlite:///{(ROOT / 'apix.db').as_posix()}"
POSTGRES_DB_URL = "postgresql+psycopg2://apix:apix@localhost:5433/apix"


def db_url() -> str:
    return os.environ.get("APIX_DB_URL", DEFAULT_DB_URL)


def db_path() -> Path:
    """Where the SQLite file lives.

    Overridable with APIX_DB_PATH so a test run, a dry run or a second
    environment can use its own database. Without this the dry-run harness
    deleted the live one -- taking every operator account and API key with it.
    """
    override = os.environ.get("APIX_DB_PATH")
    return Path(override) if override else (ROOT / "apix.db")


@dataclass(frozen=True)
class Route:
    code: str
    origin: str
    destination: str
    origin_city: str
    destination_city: str
    weight: float | None


@dataclass(frozen=True)
class Basket:
    method_version: str
    base_period_days: int
    observation_slot_ist: str
    windows: list[int]
    routes: list[Route]
    spec: dict
    confidence: dict

    @property
    def cells_per_day(self) -> int:
        return len(self.routes) * len(self.windows)

    @property
    def weights_provisional(self) -> bool:
        """True when any route lacks a real DGCA-derived weight."""
        return any(r.weight is None for r in self.routes)

    def effective_weights(self) -> dict[str, float]:
        """Normalised weights. Falls back to equal weighting when the DGCA
        city-pair data has not been loaded yet. The caller is expected to
        propagate `weights_provisional` onto every row it writes."""
        if self.weights_provisional:
            n = len(self.routes)
            return {r.code: 1.0 / n for r in self.routes}
        total = sum(r.weight for r in self.routes)
        if total <= 0:
            raise ValueError("route weights sum to zero")
        return {r.code: r.weight / total for r in self.routes}

    def route(self, code: str) -> Route:
        for r in self.routes:
            if r.code == code:
                return r
        raise KeyError(f"unknown route: {code}")


@lru_cache(maxsize=1)
def load_basket(path: Path | None = None) -> Basket:
    p = path or (CONFIG_DIR / "basket.yml")
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    return Basket(
        method_version=str(raw["method_version"]),
        base_period_days=int(raw["base_period_days"]),
        observation_slot_ist=str(raw["observation_slot_ist"]),
        windows=[int(w) for w in raw["windows"]],
        routes=[Route(**r) for r in raw["routes"]],
        spec=raw.get("spec", {}),
        confidence=raw.get("confidence", {}),
    )


@lru_cache(maxsize=1)
def load_registry(path: Path | None = None) -> dict:
    p = path or (COMPLIANCE_DIR / "registry.yml")
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def departure_date(observation_date: date, window_days: int) -> date:
    """T+N: the departure date a given booking window points at."""
    return observation_date + timedelta(days=window_days)
