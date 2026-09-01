"""Seeds the two buildathon demo accounts (one per role). Idempotent --
safe to run again after a password rotation.

    DEMO_ANALYST_PASSWORD=... DEMO_REVIEWER_PASSWORD=... \
        backend/.venv/bin/python backend/scripts/seed_demo_users.py

Both passwords MUST be supplied through the environment. There are
deliberately no defaults in this file: a default committed here would be
a working credential for every deployment seeded from this repository,
readable by anyone with access to the source or its history. Missing
configuration fails loudly instead (see SeedConfigurationError).

Passwords are hashed with the same PBKDF2-HMAC-SHA256 helper the login
path uses (app/auth/security.py) and only the salt and hash are stored --
the plaintext never reaches the database and is never logged here.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth.security import hash_password
from app.investigation.runners.deterministic import connect

DEMO_USERS = [
    {
        "email": "analyst@ledgerlens.dev",
        "role": "analyst",
        "password_env": "DEMO_ANALYST_PASSWORD",
    },
    {
        "email": "reviewer@ledgerlens.dev",
        "role": "reviewer",
        "password_env": "DEMO_REVIEWER_PASSWORD",
    },
]


class SeedConfigurationError(RuntimeError):
    """A required demo password was not supplied. Raised before any
    database write happens, so a partial seed is impossible."""


def resolve_passwords(env=None) -> dict[str, str]:
    """Every demo password, or a clear error naming what is missing.

    Resolved for ALL users up front, deliberately: seeding the analyst
    and only then discovering the reviewer variable is missing would
    leave the database half-rotated.
    """
    environment = os.environ if env is None else env

    missing = [
        spec["password_env"]
        for spec in DEMO_USERS
        if not (environment.get(spec["password_env"]) or "").strip()
    ]
    if missing:
        raise SeedConfigurationError(
            "Missing required demo password environment variable(s): "
            + ", ".join(missing)
            + ". Set them before seeding -- this script has no built-in "
            "defaults on purpose, so that no working credential is ever "
            "committed to the repository."
        )

    return {spec["email"]: environment[spec["password_env"]] for spec in DEMO_USERS}


def seed() -> None:
    # Fails here, before opening a connection, if anything is unset.
    passwords = resolve_passwords()

    with connect() as conn:
        with conn.cursor() as cur:
            for spec in DEMO_USERS:
                salt, password_hash = hash_password(passwords[spec["email"]])

                cur.execute(
                    """
                    insert into users (email, password_hash, password_salt, role)
                    values (%s, %s, %s, %s)
                    on conflict (email) do update
                        set password_hash = excluded.password_hash,
                            password_salt = excluded.password_salt,
                            role = excluded.role
                    """,
                    (spec["email"], password_hash, salt, spec["role"]),
                )
                print(f"seeded {spec['role']}: {spec['email']}")

            conn.commit()


if __name__ == "__main__":
    try:
        seed()
    except SeedConfigurationError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
