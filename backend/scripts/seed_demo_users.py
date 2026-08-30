"""Seeds the two buildathon demo accounts (one per role). Idempotent --
safe to run again after a password rotation.

    backend/.venv/bin/python backend/scripts/seed_demo_users.py

Demo passwords are dev-only defaults, never checked into the frontend
and never logged here beyond the confirmation line below. Override them
for any real deployment via DEMO_ANALYST_PASSWORD / DEMO_REVIEWER_PASSWORD.
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
        "default_password": "Analyst!Demo2026",
    },
    {
        "email": "reviewer@ledgerlens.dev",
        "role": "reviewer",
        "password_env": "DEMO_REVIEWER_PASSWORD",
        "default_password": "Reviewer!Demo2026",
    },
]


def seed() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            for spec in DEMO_USERS:
                password = os.getenv(spec["password_env"], spec["default_password"])
                salt, password_hash = hash_password(password)

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
    seed()
