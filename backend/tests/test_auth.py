"""End-to-end auth checks against the real FastAPI app + live DB via
fastapi.testclient.TestClient (the one place this test suite reaches
through the actual HTTP/cookie layer instead of calling service
functions directly -- login/session/role enforcement is only real when
exercised through the ASGI app, cookies included). Throwaway
TEST-AUTH-* users/investigations only; cleans up after itself.

Run directly: python backend/tests/test_auth.py
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

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


if __name__ == "__main__":
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"\n{len(tests)} passed")
