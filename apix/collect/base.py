"""
The extension point.

Every source -- live portal, replay generator, manual panel -- implements
SourceAdapter. Adding an airline is one class, not a new pipeline. That claim
is only true if nothing downstream of here knows which adapter produced a row,
so adapters return RawResponse and nothing else.
"""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date

from apix.vocab import ObsStatus, SourceClass


@dataclass
class RawResponse:
    """What an adapter hands back. Written to Bronze verbatim, before parsing."""

    source_id: str
    source_class: SourceClass
    observation_date: date
    route_code: str
    window_days: int
    departure_date: date

    fetch_status: ObsStatus
    payload: str | None = None
    request_url: str | None = None
    user_agent: str | None = None
    http_status: int | None = None
    error_detail: str | None = None
    extra: dict = field(default_factory=dict)

    @property
    def payload_sha256(self) -> str | None:
        if self.payload is None:
            return None
        return hashlib.sha256(self.payload.encode("utf-8", "replace")).hexdigest()


class SourceAdapter(ABC):
    source_id: str = "abstract"
    source_class: SourceClass = SourceClass.LIVE

    @abstractmethod
    def search(
        self, route_code: str, window_days: int, observation_date: date
    ) -> RawResponse:
        """Fetch one cell. Must return a RawResponse even on failure --
        a BLOCKED row is data, and a silent exception is a lost day."""
        raise NotImplementedError
