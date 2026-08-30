"""DB-backed user/session lookups -- same connect()/cursor pattern every
other service in this codebase already uses (see
app/investigation/services/*), just against the users/sessions tables
added by migration 006."""

from datetime import datetime, timedelta, timezone
from typing import Any

from app.auth.security import generate_session_token, hash_password, verify_password

SESSION_TTL = timedelta(hours=12)


def get_user_by_email(cur, email: str) -> dict[str, Any] | None:
    cur.execute(
        "select id, email, password_hash, password_salt, role from users where email = %s",
        (email,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "id": str(row[0]),
        "email": row[1],
        "password_hash": row[2],
        "password_salt": row[3],
        "role": row[4],
    }


def authenticate(cur, email: str, password: str) -> dict[str, Any] | None:
    """Returns the public user shape (never the hash/salt) on success,
    None on either an unknown email or a wrong password -- the caller
    must not distinguish the two in its response, or it leaks which
    emails are registered."""
    user = get_user_by_email(cur, email)
    if user is None:
        return None
    if not verify_password(password, user["password_salt"], user["password_hash"]):
        return None
    return {"id": user["id"], "email": user["email"], "role": user["role"]}


def create_user(cur, email: str, password: str) -> dict[str, Any]:
    """Self-registration only ever creates an Analyst -- role is not a
    parameter, so no caller (including a compromised request body) can
    pass anything else through to the insert."""
    salt, password_hash = hash_password(password)
    cur.execute(
        """
        insert into users (email, password_hash, password_salt, role)
        values (%s, %s, %s, 'analyst')
        returning id, email, role
        """,
        (email, password_hash, salt),
    )
    row = cur.fetchone()
    return {"id": str(row[0]), "email": row[1], "role": row[2]}


def create_session(cur, user_id: str) -> tuple[str, datetime]:
    token = generate_session_token()
    expires_at = datetime.now(timezone.utc) + SESSION_TTL
    cur.execute(
        "insert into sessions (token, user_id, expires_at) values (%s, %s, %s)",
        (token, user_id, expires_at),
    )
    return token, expires_at


def get_user_by_session(cur, token: str) -> dict[str, Any] | None:
    cur.execute(
        """
        select u.id, u.email, u.role
        from sessions s
        join users u on u.id = s.user_id
        where s.token = %s and s.expires_at > now()
        """,
        (token,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return {"id": str(row[0]), "email": row[1], "role": row[2]}


def delete_session(cur, token: str) -> None:
    cur.execute("delete from sessions where token = %s", (token,))
