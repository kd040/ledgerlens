"""Demo-account seeding must never fall back to a built-in password.

A default committed in backend/scripts/seed_demo_users.py would be a
working credential for every deployment seeded from this repository, and
readable by anyone with access to the source or its history. These tests
pin that contract: the passwords come from the environment or the seed
refuses to run.

Throwaway TEST-SEED-* rows only; cleans up after itself and never touches
the real analyst@/reviewer@ledgerlens.dev accounts.

Run directly: python backend/tests/test_seed_demo_users.py
"""

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth.security import hash_password, verify_password
from app.investigation.runners.deterministic import connect

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "seed_demo_users.py"


def _load_seed_module():
    """The seeder is a script, not a package module -- load it by path so
    the test exercises the real file rather than a copy of its logic."""
    spec = importlib.util.spec_from_file_location("seed_demo_users", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed_demo_users = _load_seed_module()


# ------------------------------------------------------------------
# The file itself must carry no credential
# ------------------------------------------------------------------

def test_seed_script_contains_no_hardcoded_password():
    source = _SCRIPT.read_text()
    assert "default_password" not in source, "a built-in password default came back"
    for leaked in ("Analyst!Demo2026", "Reviewer!Demo2026"):
        assert leaked not in source, f"{leaked!r} is still committed in the seed script"


def test_demo_users_declare_env_vars_and_no_defaults():
    for spec in seed_demo_users.DEMO_USERS:
        assert spec["password_env"] in (
            "DEMO_ANALYST_PASSWORD",
            "DEMO_REVIEWER_PASSWORD",
        )
        assert "default_password" not in spec, spec


# ------------------------------------------------------------------
# Missing configuration fails clearly, and BEFORE any database write
# ------------------------------------------------------------------

def test_missing_analyst_password_raises_configuration_error():
    try:
        seed_demo_users.resolve_passwords(env={"DEMO_REVIEWER_PASSWORD": "r-secret"})
        raise AssertionError("expected SeedConfigurationError")
    except seed_demo_users.SeedConfigurationError as error:
        assert "DEMO_ANALYST_PASSWORD" in str(error)
        assert "DEMO_REVIEWER_PASSWORD" not in str(error)


def test_missing_reviewer_password_raises_configuration_error():
    try:
        seed_demo_users.resolve_passwords(env={"DEMO_ANALYST_PASSWORD": "a-secret"})
        raise AssertionError("expected SeedConfigurationError")
    except seed_demo_users.SeedConfigurationError as error:
        assert "DEMO_REVIEWER_PASSWORD" in str(error)
        assert "DEMO_ANALYST_PASSWORD" not in str(error)


def test_both_missing_names_both_variables():
    try:
        seed_demo_users.resolve_passwords(env={})
        raise AssertionError("expected SeedConfigurationError")
    except seed_demo_users.SeedConfigurationError as error:
        assert "DEMO_ANALYST_PASSWORD" in str(error)
        assert "DEMO_REVIEWER_PASSWORD" in str(error)


def test_blank_or_whitespace_password_is_treated_as_missing():
    """An empty .env line ("DEMO_ANALYST_PASSWORD=") must not seed an
    account with an empty password."""
    for blank in ("", "   ", "\t", "\n"):
        try:
            seed_demo_users.resolve_passwords(
                env={"DEMO_ANALYST_PASSWORD": blank, "DEMO_REVIEWER_PASSWORD": "r-secret"}
            )
            raise AssertionError(f"expected SeedConfigurationError for {blank!r}")
        except seed_demo_users.SeedConfigurationError as error:
            assert "DEMO_ANALYST_PASSWORD" in str(error)


def test_configuration_error_never_echoes_the_supplied_password():
    try:
        seed_demo_users.resolve_passwords(env={"DEMO_REVIEWER_PASSWORD": "sup3r-s3cret-value"})
        raise AssertionError("expected SeedConfigurationError")
    except seed_demo_users.SeedConfigurationError as error:
        assert "sup3r-s3cret-value" not in str(error)


# ------------------------------------------------------------------
# Supplied passwords resolve, and hash the way login expects
# ------------------------------------------------------------------

def test_environment_passwords_resolve_for_both_accounts():
    resolved = seed_demo_users.resolve_passwords(
        env={"DEMO_ANALYST_PASSWORD": "a-secret", "DEMO_REVIEWER_PASSWORD": "r-secret"}
    )
    assert resolved == {
        "analyst@ledgerlens.dev": "a-secret",
        "reviewer@ledgerlens.dev": "r-secret",
    }


def test_upsert_stores_only_a_verifiable_hash_and_never_the_plaintext():
    """The seeding write path, exercised against a throwaway row: same
    hash_password helper, same on-conflict upsert, no plaintext stored."""
    email = "test-seed-user@ledgerlens.test"
    password = "N0t-A-Real-Password!"

    with connect() as conn:
        with conn.cursor() as cur:
            try:
                salt, password_hash = hash_password(password)
                cur.execute(
                    """
                    insert into users (email, password_hash, password_salt, role)
                    values (%s, %s, %s, 'analyst')
                    on conflict (email) do update
                        set password_hash = excluded.password_hash,
                            password_salt = excluded.password_salt,
                            role = excluded.role
                    """,
                    (email, password_hash, salt),
                )
                conn.commit()

                cur.execute(
                    "select password_hash, password_salt, role from users where email = %s",
                    (email,),
                )
                stored_hash, stored_salt, role = cur.fetchone()

                assert verify_password(password, stored_salt, stored_hash)
                assert not verify_password("wrong-password", stored_salt, stored_hash)
                # Nothing resembling the plaintext is persisted anywhere.
                assert password not in stored_hash
                assert password not in stored_salt
                assert role == "analyst"

                # Re-seeding rotates the credential rather than duplicating
                # the row -- the upsert behaviour the script relies on.
                new_salt, new_hash = hash_password("Rotated-Password!")
                cur.execute(
                    """
                    insert into users (email, password_hash, password_salt, role)
                    values (%s, %s, %s, 'analyst')
                    on conflict (email) do update
                        set password_hash = excluded.password_hash,
                            password_salt = excluded.password_salt,
                            role = excluded.role
                    """,
                    (email, new_hash, new_salt),
                )
                conn.commit()

                cur.execute("select count(*) from users where email = %s", (email,))
                assert cur.fetchone()[0] == 1, "re-seeding created a duplicate user"

                cur.execute(
                    "select password_hash, password_salt from users where email = %s", (email,)
                )
                rotated_hash, rotated_salt = cur.fetchone()
                assert verify_password("Rotated-Password!", rotated_salt, rotated_hash)
                assert not verify_password(password, rotated_salt, rotated_hash)
            finally:
                cur.execute("delete from users where email = %s", (email,))
                conn.commit()


def test_salts_are_unique_per_user():
    """Two accounts seeded with the SAME password must not share a hash --
    otherwise one cracked demo password would reveal both."""
    salt_a, hash_a = hash_password("identical-password")
    salt_b, hash_b = hash_password("identical-password")
    assert salt_a != salt_b
    assert hash_a != hash_b


if __name__ == "__main__":
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"\n{len(tests)} passed")
