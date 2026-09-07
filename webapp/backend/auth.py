"""
Authentication: admin sessions and consumer API keys.

The two secrets are hashed differently, on purpose.

A password is human-chosen and low-entropy, so it must be expensive to guess:
scrypt with a per-user salt.

An API key is 256 bits of OS randomness, so there is nothing to guess, and it
is checked on every request — a slow hash there is a DoS vector rather than a
security gain. SHA-256.

Neither is ever written to the database, the logs or a response body. A key is
shown to its creator once, at creation.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

ROOT = Path(__file__).resolve().parents[2]

# scrypt cost. n=2**14 is ~50ms per hash here: slow enough to make offline
# guessing expensive, fast enough that a login does not feel broken.
SCRYPT_N, SCRYPT_R, SCRYPT_P, DK_LEN = 2 ** 14, 8, 1, 32

SESSION_COOKIE = "apix_session"
SESSION_MAX_AGE = 8 * 3600          # a working day, then log in again
MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15

KEY_PREFIX = "apix_live_"
KEY_BYTES = 32                      # 256 bits


# ---------------------------------------------------------------------------
# the signing secret
# ---------------------------------------------------------------------------
def _secret_path() -> Path:
    return ROOT / ".apix_secret"


def session_secret() -> str:
    """Persisted outside the repo and outside the database.

    Generated on first run rather than shipped. A committed secret is not a
    secret, and a secret that changes every restart logs everybody out on every
    deploy. .gitignore excludes this file.
    """
    p = _secret_path()
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    s = secrets.token_urlsafe(48)
    p.write_text(s, encoding="utf-8")
    try:
        p.chmod(0o600)
    except OSError:
        pass                        # best effort; Windows has no chmod
    return s


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(session_secret(), salt="apix-session-v1")


# ---------------------------------------------------------------------------
# passwords
# ---------------------------------------------------------------------------
def hash_password(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    salt = salt or os.urandom(16)
    h = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                       n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=DK_LEN)
    return salt, h


def verify_password(password: str, salt: bytes, expected: bytes) -> bool:
    _, h = hash_password(password, salt)
    return hmac.compare_digest(h, expected)


# ---------------------------------------------------------------------------
# users
# ---------------------------------------------------------------------------
@dataclass
class User:
    id: int
    email: str
    display_name: str
    role: str


def create_user(conn: sqlite3.Connection, email: str, display_name: str,
                password: str, role: str = "admin") -> User:
    if len(password) < 10:
        raise ValueError("password must be at least 10 characters")
    salt, h = hash_password(password)
    with conn:
        cur = conn.execute(
            """INSERT INTO web_user (email, display_name, pw_salt, pw_hash, role)
               VALUES (?,?,?,?,?)""",
            (email.strip().lower(), display_name, salt, h, role))
    return User(cur.lastrowid, email.strip().lower(), display_name, role)


def set_password(conn: sqlite3.Connection, email: str, password: str) -> bool:
    """Change a password in place, keeping the account and everything that
    references it. Deleting and recreating would orphan the API keys the
    account issued, and their history is part of the audit trail."""
    if len(password) < 10:
        raise ValueError("password must be at least 10 characters")
    salt, h = hash_password(password)
    with conn:
        cur = conn.execute(
            """UPDATE web_user SET pw_salt=?, pw_hash=?, failed_logins=0,
                                   locked_until=NULL
               WHERE email=?""",
            (salt, h, email.strip().lower()))
    return cur.rowcount > 0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def authenticate(conn: sqlite3.Connection, email: str, password: str) -> tuple[User | None, str]:
    """Returns (user, reason). A failure never says which half was wrong."""
    row = conn.execute(
        "SELECT * FROM web_user WHERE email = ?", (email.strip().lower(),)
    ).fetchone()

    if row is None:
        # Hash anyway, so a missing account and a wrong password take the same
        # time and cannot be told apart by a stopwatch.
        hash_password(password, b"\x00" * 16)
        return None, "Email or password is incorrect."

    if not row["is_active"]:
        return None, "This account has been deactivated."

    if row["locked_until"]:
        until = datetime.fromisoformat(row["locked_until"])
        if until > _now():
            mins = max(1, int((until - _now()).total_seconds() // 60) + 1)
            return None, f"Too many attempts. Try again in {mins} minute(s)."

    if not verify_password(password, row["pw_salt"], row["pw_hash"]):
        failed = row["failed_logins"] + 1
        lock = (_now() + timedelta(minutes=LOCKOUT_MINUTES)).isoformat() \
            if failed >= MAX_FAILED_LOGINS else None
        with conn:
            conn.execute("UPDATE web_user SET failed_logins=?, locked_until=? WHERE id=?",
                         (failed, lock, row["id"]))
        if lock:
            return None, f"Too many attempts. Locked for {LOCKOUT_MINUTES} minutes."
        return None, "Email or password is incorrect."

    with conn:
        conn.execute("""UPDATE web_user SET failed_logins=0, locked_until=NULL,
                        last_login_at=? WHERE id=?""", (_now().isoformat(), row["id"]))
    return User(row["id"], row["email"], row["display_name"], row["role"]), "ok"


# ---------------------------------------------------------------------------
# sessions
# ---------------------------------------------------------------------------
def issue_session(user: User) -> str:
    return _serializer().dumps({"uid": user.id, "email": user.email})


def read_session(conn: sqlite3.Connection, token: str | None) -> User | None:
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=SESSION_MAX_AGE)
    except (SignatureExpired, BadSignature):
        return None
    row = conn.execute("SELECT * FROM web_user WHERE id=? AND is_active=1",
                       (data.get("uid"),)).fetchone()
    if row is None:
        return None                 # deactivated since the cookie was issued
    return User(row["id"], row["email"], row["display_name"], row["role"])


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------
@dataclass
class KeyCheck:
    ok: bool
    key_id: int | None
    label: str | None
    scopes: list[str]
    reason: str
    rate_per_min: int = 60


def _sha(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def mint_api_key(conn: sqlite3.Connection, label: str, organisation: str | None,
                 created_by: int | None, scopes: str = "read:index",
                 rate_per_min: int = 60, expires_days: int | None = None) -> tuple[str, dict]:
    """Create a key. Returns (the key, the stored row) — the key is returned
    here and nowhere else, ever again."""
    raw = KEY_PREFIX + secrets.token_urlsafe(KEY_BYTES)
    prefix = raw[:len(KEY_PREFIX) + 8]
    expires = ((_now() + timedelta(days=expires_days)).isoformat()
               if expires_days else None)
    with conn:
        cur = conn.execute(
            """INSERT INTO api_key (prefix, key_sha256, label, organisation,
                                    scopes, rate_per_min, created_by, expires_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (prefix, _sha(raw), label, organisation, scopes, rate_per_min,
             created_by, expires))
    row = dict(conn.execute("SELECT * FROM api_key WHERE id=?", (cur.lastrowid,)).fetchone())
    return raw, row


def check_api_key(conn: sqlite3.Connection, raw: str | None) -> KeyCheck:
    """Every distinct failure gets its own message. A consumer whose key was
    revoked should not spend an afternoon thinking they typed it wrong."""
    if not raw:
        return KeyCheck(False, None, None, [], "No API key supplied. Send it as "
                        "'Authorization: Bearer <key>' or 'X-API-Key: <key>'.")
    raw = raw.strip()
    row = conn.execute("SELECT * FROM api_key WHERE key_sha256 = ?", (_sha(raw),)).fetchone()
    if row is None:
        return KeyCheck(False, None, None, [], "That API key is not recognised.")
    if row["revoked_at"]:
        return KeyCheck(False, row["id"], row["label"], [],
                        f"This key was revoked on {row['revoked_at'][:10]}.")
    if row["expires_at"] and datetime.fromisoformat(row["expires_at"]) < _now():
        return KeyCheck(False, row["id"], row["label"], [],
                        f"This key expired on {row['expires_at'][:10]}.")
    return KeyCheck(True, row["id"], row["label"],
                    [s.strip() for s in row["scopes"].split(",") if s.strip()],
                    "ok", row["rate_per_min"])


def record_use(conn: sqlite3.Connection, key_id: int | None, path: str,
               status_code: int, ip: str | None) -> None:
    with conn:
        if key_id is not None:
            conn.execute("""UPDATE api_key SET last_used_at=?, request_count=request_count+1
                            WHERE id=?""", (_now().isoformat(), key_id))
        conn.execute("""INSERT INTO api_access_log (api_key_id, path, status_code, ip, at_utc)
                        VALUES (?,?,?,?,?)""",
                     (key_id, path, status_code, ip, _now().isoformat()))


def revoke_key(conn: sqlite3.Connection, key_id: int, reason: str) -> bool:
    with conn:
        cur = conn.execute(
            """UPDATE api_key SET revoked_at=?, revoked_reason=?
               WHERE id=? AND revoked_at IS NULL""",
            (_now().isoformat(), reason, key_id))
    return cur.rowcount > 0
