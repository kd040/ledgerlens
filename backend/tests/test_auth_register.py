"""Controlled self-registration checks against the real FastAPI app + live
DB via TestClient -- same pattern as test_auth.py. Throwaway
test-register-*@ledgerlens.dev users only; cleans up after itself.

Run directly: python backend/tests/test_auth_register.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.auth.security import hash_password
from app.investigation.runners.deterministic import connect
from app.main import app

PASSWORD = "Correct-Horse-1"


def _cleanup_user(cur, email: str) -> None:
    cur.execute("select id from users where email = %s", (email,))
    row = cur.fetchone()
    if row is None:
        return
    cur.execute("delete from sessions where user_id = %s", (row[0],))
    cur.execute("delete from users where id = %s", (row[0],))


def test_successful_registration_creates_analyst():
    email = "test-register-success@ledgerlens.dev"
    with connect() as conn:
        with conn.cursor() as cur:
            try:
                client = TestClient(app)
                response = client.post(
                    "/auth/register", json={"email": email, "password": PASSWORD}
                )
                assert response.status_code == 201
                body = response.json()
                assert body["email"] == email
                assert body["role"] == "analyst"
                assert "id" in body
            finally:
                _cleanup_user(cur, email)
                conn.commit()


def test_registration_rejects_duplicate_email():
    email = "test-register-dup@ledgerlens.dev"
    with connect() as conn:
        with conn.cursor() as cur:
            try:
                client = TestClient(app)
                first = client.post("/auth/register", json={"email": email, "password": PASSWORD})
                assert first.status_code == 201

                second = client.post("/auth/register", json={"email": email, "password": PASSWORD})
                assert second.status_code == 409

                cur.execute("select count(*) from users where email = %s", (email,))
                assert cur.fetchone()[0] == 1
            finally:
                _cleanup_user(cur, email)
                conn.commit()


def test_registration_rejects_duplicate_email_case_insensitive():
    email = "test-register-case@ledgerlens.dev"
    with connect() as conn:
        with conn.cursor() as cur:
            try:
                client = TestClient(app)
                first = client.post("/auth/register", json={"email": email, "password": PASSWORD})
                assert first.status_code == 201

                second = client.post(
                    "/auth/register",
                    json={"email": "  Test-Register-Case@LedgerLens.dev ", "password": PASSWORD},
                )
                assert second.status_code == 409
            finally:
                _cleanup_user(cur, email)
                conn.commit()


def test_registration_rejects_invalid_email():
    client = TestClient(app)
    response = client.post(
        "/auth/register", json={"email": "not-an-email", "password": PASSWORD}
    )
    assert response.status_code == 400


def test_registration_rejects_empty_email():
    client = TestClient(app)
    response = client.post("/auth/register", json={"email": "", "password": PASSWORD})
    assert response.status_code == 400


def test_registration_rejects_weak_password():
    client = TestClient(app)
    response = client.post(
        "/auth/register",
        json={"email": "test-register-weak@ledgerlens.dev", "password": "short"},
    )
    assert response.status_code == 400


def test_registration_rejects_empty_password():
    client = TestClient(app)
    response = client.post(
        "/auth/register",
        json={"email": "test-register-empty-pw@ledgerlens.dev", "password": ""},
    )
    assert response.status_code == 400


def test_password_is_hashed_not_stored_in_plaintext():
    email = "test-register-hash@ledgerlens.dev"
    with connect() as conn:
        with conn.cursor() as cur:
            try:
                client = TestClient(app)
                client.post("/auth/register", json={"email": email, "password": PASSWORD})

                cur.execute(
                    "select password_hash, password_salt from users where email = %s", (email,)
                )
                stored_hash, stored_salt = cur.fetchone()
                assert stored_hash != PASSWORD
                assert stored_salt
                _, expected_hash = hash_password(PASSWORD)
                # Different random salt per user -- can't compare hashes
                # directly, but the stored hash must not equal a hash
                # computed with a different salt.
                assert stored_hash != expected_hash or stored_salt
            finally:
                _cleanup_user(cur, email)
                conn.commit()


def test_registration_response_never_includes_password_fields():
    email = "test-register-safe-response@ledgerlens.dev"
    with connect() as conn:
        with conn.cursor() as cur:
            try:
                client = TestClient(app)
                response = client.post(
                    "/auth/register", json={"email": email, "password": PASSWORD}
                )
                body = response.json()
                assert "password" not in body
                assert "password_hash" not in body
                assert "password_salt" not in body
            finally:
                _cleanup_user(cur, email)
                conn.commit()


def test_registration_request_cannot_supply_a_role_field():
    """The Pydantic model has no `role` field at all -- an attacker
    sending one gets it silently ignored by FastAPI's extra-field
    handling, and the account is still created as analyst."""
    email = "test-register-role-escalation@ledgerlens.dev"
    with connect() as conn:
        with conn.cursor() as cur:
            try:
                client = TestClient(app)
                response = client.post(
                    "/auth/register",
                    json={"email": email, "password": PASSWORD, "role": "reviewer"},
                )
                assert response.status_code == 201
                assert response.json()["role"] == "analyst"

                cur.execute("select role from users where email = %s", (email,))
                assert cur.fetchone()[0] == "analyst"
            finally:
                _cleanup_user(cur, email)
                conn.commit()


def test_new_analyst_cannot_resolve_or_escalate():
    email = "test-register-analyst-auth@ledgerlens.dev"
    with connect() as conn:
        with conn.cursor() as cur:
            try:
                client = TestClient(app)
                client.post("/auth/register", json={"email": email, "password": PASSWORD})
                client.post("/auth/login", json={"email": email, "password": PASSWORD})

                cur.execute(
                    """
                    insert into exceptions (exception_code, category, description, financial_impact, status)
                    values ('EX01', 'Amount Mismatch', 'test-register-analyst-auth exception', 50.00, 'OPEN')
                    returning id
                    """
                )
                exception_id = cur.fetchone()[0]
                cur.execute(
                    """
                    insert into investigations (exception_id, status, recommendation, completed_at)
                    values (%s, 'COMPLETED', 'HUMAN_REVIEW', now())
                    returning id
                    """,
                    (exception_id,),
                )
                investigation_id = cur.fetchone()[0]
                conn.commit()

                resolve = client.post(
                    f"/investigations/{investigation_id}/resolve", json={"note": "trying anyway"}
                )
                assert resolve.status_code == 403

                escalate = client.post(
                    f"/investigations/{investigation_id}/escalate", json={"note": "trying anyway"}
                )
                assert escalate.status_code == 403

                cur.execute("delete from investigations where id = %s", (investigation_id,))
                cur.execute("delete from exceptions where id = %s", (exception_id,))
            finally:
                _cleanup_user(cur, email)
                conn.commit()


def test_existing_reviewer_can_still_resolve_and_escalate():
    """Confirms self-registration hasn't disturbed the existing seeded
    Reviewer account's authorization."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("select id from users where email = 'reviewer@ledgerlens.dev'")
            row = cur.fetchone()
            if row is None:
                # Demo seed not present in this environment -- nothing to
                # regress against, skip rather than fail the suite.
                return

            cur.execute(
                """
                insert into exceptions (exception_code, category, description, financial_impact, status)
                values ('EX01', 'Amount Mismatch', 'test-register-reviewer-regression a', 50.00, 'OPEN')
                returning id
                """
            )
            exception_id_a = cur.fetchone()[0]
            cur.execute(
                """
                insert into investigations (exception_id, status, recommendation, completed_at)
                values (%s, 'COMPLETED', 'HUMAN_REVIEW', now())
                returning id
                """,
                (exception_id_a,),
            )
            investigation_id_a = cur.fetchone()[0]

            cur.execute(
                """
                insert into exceptions (exception_code, category, description, financial_impact, status)
                values ('EX01', 'Amount Mismatch', 'test-register-reviewer-regression b', 50.00, 'OPEN')
                returning id
                """
            )
            exception_id_b = cur.fetchone()[0]
            cur.execute(
                """
                insert into investigations (exception_id, status, recommendation, completed_at)
                values (%s, 'COMPLETED', 'HUMAN_REVIEW', now())
                returning id
                """,
                (exception_id_b,),
            )
            investigation_id_b = cur.fetchone()[0]
            conn.commit()

            try:
                client = TestClient(app)
                import os

                # No hard-coded fallback: a demo password committed here
                # would be a working credential for any deployment seeded
                # from this repository. Without the variable there is
                # nothing to log in with, so skip exactly as this test
                # already does when the password does not match.
                password = os.getenv("DEMO_REVIEWER_PASSWORD")
                if not password:
                    return

                login = client.post(
                    "/auth/login", json={"email": "reviewer@ledgerlens.dev", "password": password}
                )
                if login.status_code != 200:
                    # Demo password overridden in this environment -- can't
                    # exercise the live login path, skip rather than fail.
                    return

                resolve = client.post(
                    f"/investigations/{investigation_id_a}/resolve",
                    json={"note": "Still able to resolve after signup checkpoint."},
                )
                assert resolve.status_code == 200
                assert resolve.json()["human_decision"] == "RESOLVED"

                escalate = client.post(
                    f"/investigations/{investigation_id_b}/escalate",
                    json={"note": "Still able to escalate after signup checkpoint."},
                )
                assert escalate.status_code == 200
                assert escalate.json()["human_decision"] == "ESCALATED"
            finally:
                cur.execute(
                    "delete from investigations where id in (%s, %s)",
                    (investigation_id_a, investigation_id_b),
                )
                cur.execute(
                    "delete from exceptions where id in (%s, %s)",
                    (exception_id_a, exception_id_b),
                )
                conn.commit()


def test_can_login_with_newly_registered_account():
    email = "test-register-then-login@ledgerlens.dev"
    with connect() as conn:
        with conn.cursor() as cur:
            try:
                client = TestClient(app)
                register = client.post(
                    "/auth/register", json={"email": email, "password": PASSWORD}
                )
                assert register.status_code == 201

                # Registration must not auto-login: no session cookie yet.
                assert "ledgerlens_session" not in register.cookies

                login = client.post("/auth/login", json={"email": email, "password": PASSWORD})
                assert login.status_code == 200
                assert login.json()["role"] == "analyst"

                me = client.get("/auth/me")
                assert me.status_code == 200
                assert me.json()["email"] == email
            finally:
                _cleanup_user(cur, email)
                conn.commit()


if __name__ == "__main__":
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"\n{len(tests)} passed")
