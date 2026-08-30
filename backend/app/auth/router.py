import os
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from app.auth.dependencies import SESSION_COOKIE_NAME, get_current_user
from app.auth.store import (
    SESSION_TTL,
    authenticate,
    create_session,
    create_user,
    delete_session,
    get_user_by_email,
)
from app.investigation.runners.deterministic import connect

router = APIRouter(prefix="/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MIN_PASSWORD_LENGTH = 8


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    """No `role` field -- a self-registered account is always an Analyst
    (see create_user), so there is nothing here for a manually-edited
    request body to escalate."""

    email: str
    password: str


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=os.getenv("ENV", "development") == "production",
        path="/",
    )


@router.post("/login")
def login(body: LoginRequest, response: Response) -> dict[str, Any]:
    with connect() as conn:
        with conn.cursor() as cur:
            user = authenticate(cur, body.email.strip().lower(), body.password)

            if user is None:
                raise HTTPException(status_code=401, detail="Invalid email or password.")

            token, _expires_at = create_session(cur, user["id"])
            conn.commit()

    _set_session_cookie(response, token)
    return user


@router.post("/register", status_code=201)
def register(body: RegisterRequest) -> dict[str, Any]:
    email = body.email.strip().lower()

    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    if len(body.password) < _MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at least {_MIN_PASSWORD_LENGTH} characters.",
        )

    with connect() as conn:
        with conn.cursor() as cur:
            if get_user_by_email(cur, email) is not None:
                raise HTTPException(status_code=409, detail="An account with this email already exists.")

            user = create_user(cur, email, body.password)
            conn.commit()

    return user


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    _user: dict = Depends(get_current_user),
) -> dict[str, str]:
    token = request.cookies.get(SESSION_COOKIE_NAME)

    if token:
        with connect() as conn:
            with conn.cursor() as cur:
                delete_session(cur, token)
                conn.commit()

    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"status": "ok"}


@router.get("/me")
def me(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    return user
