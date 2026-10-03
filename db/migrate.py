"""Apply db/migrations/*.sql in order, once each.

Usage (from repo root):  python db/migrate.py
Reads DATABASE_URL from the environment or from .env in the repo root.

Rules:
  - Never edit a migration that has been merged. Add the next numbered file instead.
  - An already-applied migration whose file changed is reported as an error.
"""

import hashlib
import os
import pathlib
import sys

import psycopg

ROOT = pathlib.Path(__file__).resolve().parents[1]
MIGRATIONS = pathlib.Path(__file__).resolve().parent / "migrations"


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip("'\"")
    sys.exit("DATABASE_URL is not set (copy .env.example to .env)")


def main() -> None:
    files = sorted(MIGRATIONS.glob("*.sql"))
    with psycopg.connect(database_url(), autocommit=True) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version text PRIMARY KEY, checksum text NOT NULL,"
            " applied_at timestamptz NOT NULL DEFAULT now())"
        )
        applied = dict(conn.execute("SELECT version, checksum FROM schema_migrations").fetchall())

        for path in files:
            version = path.name
            sql = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()

            if version in applied:
                if applied[version] != checksum:
                    sys.exit(
                        f"ERROR: {version} was already applied but its contents changed. "
                        "Revert the edit and add a new migration instead."
                    )
                print(f"skip   {version}")
                continue

            print(f"apply  {version}")
            with conn.transaction():
                conn.execute(sql)
                conn.execute(
                    "INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                    (version, checksum),
                )
    print("migrations up to date")


if __name__ == "__main__":
    main()
