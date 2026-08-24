import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import psycopg


PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")


def run_migration(migration_path: Path) -> None:
    database_url = os.getenv("SUPABASE_DB_URL")

    if not database_url:
        raise RuntimeError("SUPABASE_DB_URL is not configured")

    sql = migration_path.read_text(encoding="utf-8")

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql)

    print(f"Migration applied successfully: {migration_path.name}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python scripts/run_migration.py <migration-file>"
        )

    migration_file = PROJECT_ROOT / sys.argv[1]

    if not migration_file.exists():
        raise SystemExit(f"Migration not found: {migration_file}")

    run_migration(migration_file)