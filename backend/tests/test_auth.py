"""End-to-end auth checks against the real FastAPI app + live DB via
fastapi.testclient.TestClient (the one place this test suite reaches
through the actual HTTP/cookie layer instead of calling service
functions directly -- login/session/role enforcement is only real when
exercised through the ASGI app, cookies included). Throwaway
TEST-AUTH-* users/investigations only; cleans up after itself.

Run directly: python backend/tests/test_auth.py
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.auth.security import hash_password
from app.investigation.runners.deterministic import connect
from app.main import app

ANALYST_EMAIL = "test-auth-analyst@ledgerlens.dev"
REVIEWER_EMAIL = "test-auth-reviewer@ledgerlens.dev"
PASSWORD = "Test-Auth-Password-1"


def _create_user(cur, email: str, role: str) -> str:
    salt, password_hash = hash_password(PASSWORD)
    cur.execute(
        """
        insert into users (email, password_hash, password_salt, role)
        values (%s, %s, %s, %s)
        returning id
        """,
        (email, password_hash, salt, role),
    )
    return str(cur.fetchone()[0])


def _insert_exception(cur, description: str) -> str:
    cur.execute(
        """
        insert into exceptions (exception_code, category, description, financial_impact, status)
        values ('EX01', 'Amount Mismatch', %s, 50.00, 'OPEN')
        returning id
        """,
        (description,),
    )
    return str(cur.fetchone()[0])


def _insert_investigation(cur, exception_id: str, status: str, recommendation: str) -> str:
    cur.execute(
        """
        insert into investigations (exception_id, status, recommendation, completed_at)
        values (%s, %s, %s, now())
        returning id
        """,
        (exception_id, status, recommendation),
    )
    return str(cur.fetchone()[0])


def test_login_succeeds_and_sets_httponly_cookie():
    with connect() as conn:
        with conn.cursor() as cur:
            user_id = _create_user(cur, ANALYST_EMAIL, "analyst")
            conn.commit()

            try:
                client = TestClient(app)
                response = client.post(
                    "/auth/login", json={"email": ANALYST_EMAIL, "password": PASSWORD}
                )
                assert response.status_code == 200
                body = response.json()
                assert body["email"] == ANALYST_EMAIL
                assert body["role"] == "analyst"
                assert "password" not in body
                assert "password_hash" not in body

                cookie = next(c for c in response.cookies.jar if c.name == "ledgerlens_session")
                assert cookie.value
                # httpOnly is exposed via the Set-Cookie header, not the
                # cookies jar -- confirm it directly on the raw header.
                set_cookie = response.headers.get("set-cookie", "")
                assert "httponly" in set_cookie.lower()
                assert "samesite=lax" in set_cookie.lower()
            finally:
                cur.execute("delete from sessions where user_id = %s", (user_id,))
                cur.execute("delete from users where id = %s", (user_id,))
                conn.commit()


def test_login_rejects_unknown_email():
    client = TestClient(app)
    response = client.post(
        "/auth/login", json={"email": "no-such-user@ledgerlens.dev", "password": PASSWORD}
    )
    assert response.status_code == 401
    assert "session" not in response.headers.get("set-cookie", "").lower()


def test_login_rejects_wrong_password():
    with connect() as conn:
        with conn.cursor() as cur:
            user_id = _create_user(cur, ANALYST_EMAIL, "analyst")
            conn.commit()

            try:
                client = TestClient(app)
                response = client.post(
                    "/auth/login", json={"email": ANALYST_EMAIL, "password": "wrong-password"}
                )
                assert response.status_code == 401
            finally:
                cur.execute("delete from users where id = %s", (user_id,))
                conn.commit()


def test_me_requires_authentication():
    client = TestClient(app)
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_me_returns_current_user_after_login():
    with connect() as conn:
        with conn.cursor() as cur:
            user_id = _create_user(cur, ANALYST_EMAIL, "analyst")
            conn.commit()

            try:
                client = TestClient(app)
                client.post("/auth/login", json={"email": ANALYST_EMAIL, "password": PASSWORD})
                response = client.get("/auth/me")
                assert response.status_code == 200
                assert response.json()["email"] == ANALYST_EMAIL
            finally:
                cur.execute("delete from sessions where user_id = %s", (user_id,))
                cur.execute("delete from users where id = %s", (user_id,))
                conn.commit()


def test_expired_session_is_rejected():
    with connect() as conn:
        with conn.cursor() as cur:
            user_id = _create_user(cur, ANALYST_EMAIL, "analyst")
            expired_token = "test-auth-expired-token"
            cur.execute(
                "insert into sessions (token, user_id, expires_at) values (%s, %s, %s)",
                (expired_token, user_id, datetime.now(timezone.utc) - timedelta(hours=1)),
            )
            conn.commit()

            try:
                client = TestClient(app)
                client.cookies.set("ledgerlens_session", expired_token)
                response = client.get("/auth/me")
                assert response.status_code == 401
            finally:
                cur.execute("delete from sessions where user_id = %s", (user_id,))
                cur.execute("delete from users where id = %s", (user_id,))
                conn.commit()


def test_logout_revokes_the_session():
    with connect() as conn:
        with conn.cursor() as cur:
            user_id = _create_user(cur, ANALYST_EMAIL, "analyst")
            conn.commit()

            try:
                client = TestClient(app)
                client.post("/auth/login", json={"email": ANALYST_EMAIL, "password": PASSWORD})
                assert client.get("/auth/me").status_code == 200

                logout_response = client.post("/auth/logout")
                assert logout_response.status_code == 200

                cur.execute("select count(*) from sessions where user_id = %s", (user_id,))
                assert cur.fetchone()[0] == 0

                assert client.get("/auth/me").status_code == 401
            finally:
                cur.execute("delete from sessions where user_id = %s", (user_id,))
                cur.execute("delete from users where id = %s", (user_id,))
                conn.commit()


def test_protected_endpoint_requires_authentication():
    client = TestClient(app)
    response = client.get("/investigations")
    assert response.status_code == 401


def test_analyst_can_read_investigations_but_cannot_resolve_or_escalate():
    with connect() as conn:
        with conn.cursor() as cur:
            user_id = _create_user(cur, ANALYST_EMAIL, "analyst")
            exception_id = _insert_exception(
                cur, "Payment TEST-AUTH-ANALYST expected 100.00 but settlement contains 50.00."
            )
            investigation_id = _insert_investigation(cur, exception_id, "COMPLETED", "HUMAN_REVIEW")
            conn.commit()

            try:
                client = TestClient(app)
                client.post("/auth/login", json={"email": ANALYST_EMAIL, "password": PASSWORD})

                # Analyst permissions: read access works.
                assert client.get("/investigations").status_code == 200
                assert client.get(f"/investigations/{investigation_id}").status_code == 200
                assert client.get("/exceptions").status_code == 200

                # Reviewer-only actions are forbidden, not merely hidden.
                resolve = client.post(
                    f"/investigations/{investigation_id}/resolve", json={"note": "trying anyway"}
                )
                assert resolve.status_code == 403

                escalate = client.post(
                    f"/investigations/{investigation_id}/escalate", json={"note": "trying anyway"}
                )
                assert escalate.status_code == 403

                # And the underlying data must be untouched by the attempt.
                cur.execute(
                    "select status, recommendation, human_decision from investigations where id = %s",
                    (investigation_id,),
                )
                status, recommendation, human_decision = cur.fetchone()
                assert status == "COMPLETED"
                assert recommendation == "HUMAN_REVIEW"
                assert human_decision is None
            finally:
                cur.execute("delete from investigations where exception_id = %s", (exception_id,))
                cur.execute("delete from exceptions where id = %s", (exception_id,))
                cur.execute("delete from sessions where user_id = %s", (user_id,))
                cur.execute("delete from users where id = %s", (user_id,))
                conn.commit()


def test_reviewer_can_resolve_with_note_and_audit_records_identity():
    with connect() as conn:
        with conn.cursor() as cur:
            user_id = _create_user(cur, REVIEWER_EMAIL, "reviewer")
            exception_id = _insert_exception(
                cur, "Payment TEST-AUTH-RESOLVE expected 100.00 but settlement contains 50.00."
            )
            investigation_id = _insert_investigation(cur, exception_id, "COMPLETED", "HUMAN_REVIEW")
            conn.commit()

            try:
                client = TestClient(app)
                client.post("/auth/login", json={"email": REVIEWER_EMAIL, "password": PASSWORD})

                # A required note is enforced at the HTTP layer too.
                empty_note = client.post(
                    f"/investigations/{investigation_id}/resolve", json={"note": "   "}
                )
                assert empty_note.status_code == 400

                response = client.post(
                    f"/investigations/{investigation_id}/resolve",
                    json={"note": "Verified with the merchant."},
                )
                assert response.status_code == 200
                body = response.json()
                assert body["status"] == "COMPLETED"
                assert body["recommendation"] == "RESOLVED"
                assert body["human_decision"] == "RESOLVED"

                evidence = client.get(f"/investigations/{investigation_id}/evidence").json()
                human_decisions = [e for e in evidence if e["evidence_type"] == "HUMAN_DECISION"]
                assert len(human_decisions) == 1
                assert REVIEWER_EMAIL in human_decisions[0]["description"]
                assert "REVIEWER_ACTOR" not in human_decisions[0]["description"]
            finally:
                cur.execute("delete from investigations where exception_id = %s", (exception_id,))
                cur.execute("delete from exceptions where id = %s", (exception_id,))
                cur.execute("delete from sessions where user_id = %s", (user_id,))
                cur.execute("delete from users where id = %s", (user_id,))
                conn.commit()


def test_reviewer_can_escalate_with_required_note():
    with connect() as conn:
        with conn.cursor() as cur:
            user_id = _create_user(cur, REVIEWER_EMAIL, "reviewer")
            exception_id = _insert_exception(
                cur, "Payment TEST-AUTH-ESCALATE expected 100.00 but settlement contains 50.00."
            )
            investigation_id = _insert_investigation(cur, exception_id, "COMPLETED", "HUMAN_REVIEW")
            conn.commit()

            try:
                client = TestClient(app)
                client.post("/auth/login", json={"email": REVIEWER_EMAIL, "password": PASSWORD})

                missing_note = client.post(f"/investigations/{investigation_id}/escalate", json={"note": ""})
                assert missing_note.status_code == 400

                response = client.post(
                    f"/investigations/{investigation_id}/escalate",
                    json={"note": "Needs deeper review than I can give."},
                )
                assert response.status_code == 200
                body = response.json()
                assert body["status"] == "ESCALATED"
                assert body["human_decision"] == "ESCALATED"

                evidence = client.get(f"/investigations/{investigation_id}/evidence").json()
                human_decisions = [e for e in evidence if e["evidence_type"] == "HUMAN_DECISION"]
                assert len(human_decisions) == 1
                assert "Escalated by human review" in human_decisions[0]["description"]
                assert REVIEWER_EMAIL in human_decisions[0]["description"]
            finally:
                cur.execute("delete from investigations where exception_id = %s", (exception_id,))
                cur.execute("delete from exceptions where id = %s", (exception_id,))
                cur.execute("delete from sessions where user_id = %s", (user_id,))
                cur.execute("delete from users where id = %s", (user_id,))
                conn.commit()


# ------------------------------------------------------------------
# Cross-site session cookie policy
# ------------------------------------------------------------------


def _login_set_cookie_header(env: dict[str, str]) -> str:
    """The raw Set-Cookie login emits under a given environment."""
    with connect() as conn:
        with conn.cursor() as cur:
            user_id = _create_user(cur, ANALYST_EMAIL, "analyst")
            conn.commit()
            try:
                with patch.dict(os.environ, env, clear=False):
                    client = TestClient(app)
                    response = client.post(
                        "/auth/login",
                        json={"email": ANALYST_EMAIL, "password": PASSWORD},
                    )
                assert response.status_code == 200
                return response.headers.get("set-cookie", "")
            finally:
                cur.execute("delete from sessions where user_id = %s", (user_id,))
                cur.execute("delete from users where id = %s", (user_id,))
                conn.commit()


def test_production_session_cookie_is_cross_site_capable():
    """Deployed, the frontend (Vercel) and API (Render) are different
    sites, so every authenticated request is cross-site. The browser only
    replays the session cookie on those when it is SameSite=None, and
    only accepts SameSite=None together with Secure -- so login must emit
    all three of HttpOnly, Secure and SameSite=None in production. This
    is the exact combination whose absence made /auth/me return 401 after
    a successful login."""
    header = _login_set_cookie_header({"ENV": "production"}).lower()

    assert "httponly" in header
    assert "samesite=none" in header
    assert "secure" in header


def test_development_session_cookie_stays_lax_and_insecure():
    """Locally both ends are localhost, so Lax is correct -- and Secure
    would stop the cookie being set at all over plain HTTP."""
    header = _login_set_cookie_header({"ENV": "development"}).lower()

    assert "httponly" in header
    assert "samesite=lax" in header
    assert "secure" not in header


def test_samesite_none_is_never_emitted_without_secure():
    """A SameSite=None cookie without Secure is silently discarded by
    every modern browser, which would look exactly like the bug being
    fixed. The two attributes derive from one flag, so this can never
    drift -- asserted here directly."""
    for env in ({"ENV": "production"}, {"ENV": "development"}, {"ENV": "staging"}):
        header = _login_set_cookie_header(env).lower()
        if "samesite=none" in header:
            assert "secure" in header, f"{env} emitted SameSite=None without Secure"


def test_logout_clears_the_cookie_with_matching_attributes():
    """A browser only treats a Set-Cookie as replacing an existing cookie
    when path/secure/samesite match, so logout has to repeat the same
    policy or the expired cookie lands beside the live one."""
    with connect() as conn:
        with conn.cursor() as cur:
            user_id = _create_user(cur, ANALYST_EMAIL, "analyst")
            conn.commit()
            try:
                with patch.dict(os.environ, {"ENV": "production"}, clear=False):
                    # https base URL on purpose: a Secure cookie is not
                    # replayed over plain HTTP, by the client library as
                    # by a real browser. Logging out cross-site is only
                    # exercised faithfully over TLS.
                    client = TestClient(app, base_url="https://testserver")
                    client.post(
                        "/auth/login",
                        json={"email": ANALYST_EMAIL, "password": PASSWORD},
                    )
                    logout = client.post("/auth/logout")

                assert logout.status_code == 200
                header = logout.headers.get("set-cookie", "").lower()
                assert "samesite=none" in header
                assert "secure" in header
                assert "path=/" in header
            finally:
                cur.execute("delete from sessions where user_id = %s", (user_id,))
                cur.execute("delete from users where id = %s", (user_id,))
                conn.commit()


def test_cors_allows_credentials_without_a_wildcard_origin():
    """allow_credentials only works against an explicit origin -- a
    wildcard would make the browser drop every credentialed response."""
    from app.main import allowed_origins

    origins = [origin.strip() for origin in allowed_origins.split(",")]
    assert "*" not in origins
    assert all(origin.startswith("http") for origin in origins)


if __name__ == "__main__":
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"\n{len(tests)} passed")
