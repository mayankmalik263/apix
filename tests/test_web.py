"""
The serving layer: who can read what, and what happens when they cannot.

These are the tests that matter for a system that hands an API key to a central
bank. Every one of them is a claim the admin console or the API docs makes on
screen -- if a claim is not enforced here, the screen is lying.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from webapp.backend import auth

SCHEMA_WEB = Path(__file__).resolve().parents[1] / "webapp" / "backend" / "schema_web.sql"


@pytest.fixture
def conn(tmp_path):
    c = sqlite3.connect(tmp_path / "web.db")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA_WEB.read_text(encoding="utf-8"))
    yield c
    c.close()


@pytest.fixture
def user(conn):
    return auth.create_user(conn, "op@apix.gov.in", "Operator", "a-long-enough-password")


# ---------------------------------------------------------------------------
# passwords
# ---------------------------------------------------------------------------
def test_password_is_never_stored_in_readable_form(conn, user):
    row = conn.execute("SELECT * FROM web_user WHERE id=?", (user.id,)).fetchone()
    blob = bytes(row["pw_hash"]) + bytes(row["pw_salt"])
    assert b"a-long-enough-password" not in blob
    assert len(bytes(row["pw_hash"])) == 32


def test_the_same_password_hashes_differently_for_two_users(conn, user):
    other = auth.create_user(conn, "two@apix.gov.in", "Two", "a-long-enough-password")
    a = conn.execute("SELECT pw_hash FROM web_user WHERE id=?", (user.id,)).fetchone()[0]
    b = conn.execute("SELECT pw_hash FROM web_user WHERE id=?", (other.id,)).fetchone()[0]
    assert a != b, "per-user salt is missing; one rainbow table would break both"


def test_short_passwords_are_refused(conn):
    with pytest.raises(ValueError):
        auth.create_user(conn, "x@apix.gov.in", "X", "short")


def test_wrong_password_and_unknown_account_give_the_same_message(conn, user):
    _, r1 = auth.authenticate(conn, "op@apix.gov.in", "wrong")
    _, r2 = auth.authenticate(conn, "nobody@apix.gov.in", "wrong")
    assert r1 == r2, "the error message reveals whether the account exists"


def test_account_locks_after_repeated_failures(conn, user):
    for _ in range(auth.MAX_FAILED_LOGINS):
        auth.authenticate(conn, "op@apix.gov.in", "wrong")
    who, reason = auth.authenticate(conn, "op@apix.gov.in", "a-long-enough-password")
    assert who is None, "the correct password still worked after a brute-force run"
    assert "Too many attempts" in reason


def test_a_good_login_clears_the_failure_count(conn, user):
    auth.authenticate(conn, "op@apix.gov.in", "wrong")
    auth.authenticate(conn, "op@apix.gov.in", "a-long-enough-password")
    assert conn.execute("SELECT failed_logins FROM web_user WHERE id=?",
                        (user.id,)).fetchone()[0] == 0


def test_deactivated_account_cannot_sign_in(conn, user):
    conn.execute("UPDATE web_user SET is_active=0 WHERE id=?", (user.id,))
    who, reason = auth.authenticate(conn, "op@apix.gov.in", "a-long-enough-password")
    assert who is None and "deactivated" in reason


# ---------------------------------------------------------------------------
# sessions
# ---------------------------------------------------------------------------
def test_session_round_trips(conn, user):
    assert auth.read_session(conn, auth.issue_session(user)).id == user.id


def test_a_tampered_session_is_rejected(conn, user):
    tok = auth.issue_session(user)
    assert auth.read_session(conn, tok[:-6] + "AAAAAA") is None
    assert auth.read_session(conn, "") is None
    assert auth.read_session(conn, None) is None


def test_deactivating_a_user_invalidates_their_live_session(conn, user):
    tok = auth.issue_session(user)
    conn.execute("UPDATE web_user SET is_active=0 WHERE id=?", (user.id,))
    assert auth.read_session(conn, tok) is None, "a revoked operator kept working"


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------
def test_the_key_itself_is_never_stored(conn, user):
    raw, row = auth.mint_api_key(conn, "RBI", "RBI", user.id)
    stored = conn.execute("SELECT * FROM api_key WHERE id=?", (row["id"],)).fetchone()
    assert raw not in dict(stored).values()
    assert stored["key_sha256"] != raw
    assert raw.startswith(auth.KEY_PREFIX)


def test_two_keys_are_never_the_same(conn, user):
    keys = {auth.mint_api_key(conn, f"k{i}", None, user.id)[0] for i in range(30)}
    assert len(keys) == 30


def test_a_valid_key_passes_and_a_wrong_one_does_not(conn, user):
    raw, _ = auth.mint_api_key(conn, "RBI", None, user.id)
    assert auth.check_api_key(conn, raw).ok
    assert not auth.check_api_key(conn, raw + "x").ok
    assert not auth.check_api_key(conn, None).ok
    assert not auth.check_api_key(conn, "").ok


def test_surrounding_whitespace_is_tolerated(conn, user):
    """Copied out of a terminal, a key often arrives with a newline attached."""
    raw, _ = auth.mint_api_key(conn, "RBI", None, user.id)
    assert auth.check_api_key(conn, f"  {raw}\n").ok


def test_a_revoked_key_stops_working_and_says_why(conn, user):
    raw, row = auth.mint_api_key(conn, "RBI", None, user.id)
    auth.revoke_key(conn, row["id"], "rotated")
    check = auth.check_api_key(conn, raw)
    assert not check.ok and "revoked" in check.reason


def test_revoking_twice_is_not_an_error_but_changes_nothing(conn, user):
    _, row = auth.mint_api_key(conn, "RBI", None, user.id)
    assert auth.revoke_key(conn, row["id"], "first") is True
    assert auth.revoke_key(conn, row["id"], "second") is False
    assert conn.execute("SELECT revoked_reason FROM api_key WHERE id=?",
                        (row["id"],)).fetchone()[0] == "first"


def test_an_expired_key_stops_working(conn, user):
    raw, row = auth.mint_api_key(conn, "RBI", None, user.id, expires_days=1)
    conn.execute("UPDATE api_key SET expires_at='2020-01-01T00:00:00+00:00' WHERE id=?",
                 (row["id"],))
    check = auth.check_api_key(conn, raw)
    assert not check.ok and "expired" in check.reason


def test_scopes_come_back_as_a_list(conn, user):
    raw, _ = auth.mint_api_key(conn, "RBI", None, user.id, scopes="read:index,read:lineage")
    assert auth.check_api_key(conn, raw).scopes == ["read:index", "read:lineage"]


def test_usage_is_recorded_against_the_key_not_the_key_itself(conn, user):
    raw, row = auth.mint_api_key(conn, "RBI", None, user.id)
    auth.record_use(conn, row["id"], "/v1/apix/latest", 200, "10.0.0.1")
    log = conn.execute("SELECT * FROM api_access_log").fetchone()
    assert log["api_key_id"] == row["id"]
    assert raw not in " ".join(str(v) for v in dict(log).values())
    assert conn.execute("SELECT request_count FROM api_key WHERE id=?",
                        (row["id"],)).fetchone()[0] == 1


# ---------------------------------------------------------------------------
# scope routing
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("path,expected", [
    ("/v1/apix/latest",                    "read:index"),
    ("/v1/apix/series",                    "read:index"),
    ("/v1/stats/summary",                  "read:index"),
    ("/v1/lineage/2026-09-07/DEL-BOM/21",  "read:lineage"),
    ("/v1/compliance/report",              "read:compliance"),
    ("/v1/bronze/stats",                   "read:compliance"),
])
def test_each_endpoint_family_demands_its_own_scope(path, expected):
    from webapp.backend.deps import scope_for
    assert scope_for(path) == expected
