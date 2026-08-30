"""Reusable FastAPI dependencies enforcing authentication/authorization
server-side. Applied at router level (see app/main.py) so hiding a
frontend button is never the only thing standing between a request and
a protected endpoint."""

from fastapi import Depends, HTTPException, Request

from app.auth.store import get_user_by_session
from app.investigation.runners.deterministic import connect

SESSION_COOKIE_NAME = "ledgerlens_session"


def get_current_user(request: Request) -> dict:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated.")

    with connect() as conn:
        with conn.cursor() as cur:
            user = get_user_by_session(cur, token)

    if user is None:
        raise HTTPException(status_code=401, detail="Session is invalid or has expired.")

    return user


def require_reviewer(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "reviewer":
        raise HTTPException(
            status_code=403,
            detail="This action requires Reviewer authorization.",
        )
    return user
