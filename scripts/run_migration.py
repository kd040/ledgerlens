import os
from pathlib import Path

from dotenv import load_dotenv
import psycopg


PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")

database_url = os.getenv("SUPABASE_DB_URL")

if not database_url:
    raise RuntimeError("SUPABASE_DB_URL is not configured")

migration_path = (
    PROJECT_ROOT
    / "database"
    / "migrations"
    / "001_initial_financial_schema.sql"
)

sql = migration_path.read_text(encoding="utf-8")

with psycopg.connect(database_url) as connection:
    with connection.cursor() as cursor:
        cursor.execute(sql)

print("Migration 001 applied successfully.")