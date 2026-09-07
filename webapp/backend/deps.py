"""
Who is allowed to read what.

THREE TIERS, AND THE REASON FOR EACH
    public   The published index. Open, rate limited — a statistical series
             is public information.

    keyed    The documented API for institutional consumers. The key exists so
             bulk access is attributable, rate-limitable and revocable.

    admin    Anything that changes the system: minting keys, forcing a run,
             reading the access log. Session cookie; accounts are created from
             a shell, not signed up for.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import Depends, HTTPException, Request

from webapp.backend import auth

ROOT = Path(__file__).resolve().parents[2]
from apix.config import db_path

DB_PATH = db_path()


def db() -> sqlite3.Connection:
    """One connection per request.

    check_same_thread=False is required, not optional: FastAPI runs sync
    dependencies in a threadpool, so the thread that opens the connection is
    not always the thread that closes it. Without this every request that
    touches the database raises ProgrammingError on teardown.

    It is safe here because a connection is created, used and closed inside a
    single request and is never shared between them.
    """
    c = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    c.row_factory = sqlite3.Row
    try:
        yield c
    finally:
        c.close()


def client_ip(request: Request) -> str:
    # Behind a proxy the socket address is the proxy. Trust the first hop only.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def current_user(request: Request, conn: sqlite3.Connection = Depends(db)) -> auth.User | None:
    return auth.read_session(conn, request.cookies.get(auth.SESSION_COOKIE))


def require_admin(request: Request,
                  conn: sqlite3.Connection = Depends(db)) -> auth.User:
    user = auth.read_session(conn, request.cookies.get(auth.SESSION_COOKIE))
    if user is None:
        raise HTTPException(401, "Sign in to continue.")
    if user.role != "admin":
        raise HTTPException(403, "This action needs an admin account.")
    return user


def _extract_key(request: Request) -> str | None:
    """Accept both conventions. A consumer should not have to guess."""
    hdr = request.headers.get("authorization")
    if hdr and hdr.lower().startswith("bearer "):
        return hdr[7:].strip()
    return request.headers.get("x-api-key") or request.query_params.get("api_key")


def require_api_key(request: Request,
                    conn: sqlite3.Connection = Depends(db)) -> auth.KeyCheck:
    """The documented API. An admin session also works, so an operator testing
    the docs page in their browser is not locked out of their own system."""
    raw = _extract_key(request)

    if raw is None:
        user = auth.read_session(conn, request.cookies.get(auth.SESSION_COOKIE))
        if user is not None:
            return auth.KeyCheck(True, None, f"session:{user.email}",
                                 ["read:index", "read:lineage"], "ok", 600)

    check = auth.check_api_key(conn, raw)
    auth.record_use(conn, check.key_id, request.url.path,
                    200 if check.ok else 401, client_ip(request))
    if not check.ok:
        raise HTTPException(401, check.reason,
                            headers={"WWW-Authenticate": "Bearer"})
    return check


# Which scope each family of endpoints needs. Declared here, in one table,
# rather than scattered across decorators -- the data endpoints are mounted
# twice (open at /public, keyed at /v1) and a per-endpoint dependency would
# have to be right in both places or wrong in one.
SCOPE_BY_PREFIX = (
    ("/v1/lineage",    "read:lineage"),
    ("/v1/compliance", "read:compliance"),
    ("/v1/bronze",     "read:compliance"),
)
DEFAULT_SCOPE = "read:index"


def scope_for(path: str) -> str:
    for prefix, scope in SCOPE_BY_PREFIX:
        if path.startswith(prefix):
            return scope
    return DEFAULT_SCOPE


def require_scoped_access(request: Request,
                          key: auth.KeyCheck = Depends(require_api_key)) -> auth.KeyCheck:
    """Validate the key, and that its scopes cover this endpoint."""
    needed = scope_for(request.url.path)
    if needed not in key.scopes:
        raise HTTPException(
            403,
            f"This key does not carry the '{needed}' scope required by "
            f"{request.url.path}. It has: {', '.join(key.scopes) or 'none'}.")
    return key
