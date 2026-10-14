import argparse
import hashlib
from pathlib import Path

import psycopg


def apply_migrations(database_url: str, directory: Path) -> None:
    migrations = sorted(directory.glob("[0-9][0-9][0-9]_*.sql"))
    if not migrations:
        raise RuntimeError("No numbered SQL migrations were found")
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version text PRIMARY KEY, sha256 text NOT NULL)"
        )
        for migration in migrations:
            sql = migration.read_text(encoding="utf-8")
            digest = hashlib.sha256(sql.encode("utf-8")).hexdigest()
            current = connection.execute(
                "SELECT sha256 FROM schema_migrations WHERE version = %s",
                (migration.name,),
            ).fetchone()
            if current is not None:
                if current[0] != digest:
                    raise RuntimeError(f"Applied migration changed: {migration.name}")
                continue
            with connection.transaction():
                connection.execute(sql)
                connection.execute(
                    "INSERT INTO schema_migrations (version, sha256) VALUES (%s, %s)",
                    (migration.name, digest),
                )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    database_url = __import__("os").environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    apply_migrations(database_url, args.directory)


if __name__ == "__main__":
    main()
