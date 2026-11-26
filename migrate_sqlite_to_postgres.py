"""Back up and copy an existing local SQLite database to an empty Supabase DB.

This is an explicit owner-run command. It never deletes or modifies the source
SQLite file, and it refuses to merge into a destination with user records.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import sqlite3
from pathlib import Path

from database import connect_db, initialize_database, is_postgres_enabled


TABLES_IN_ORDER = (
    "courses",
    "users",
    "questions",
    "progress",
    "bounty_records",
    "user_profiles",
    "question_rotation",
)
DESTINATION_MUST_BE_EMPTY = (
    "users", "courses", "questions", "progress", "bounty_records", "user_profiles", "question_rotation"
)
UPSERT_REFERENCE_TABLES = {"courses", "questions"}


def _quote(identifier: str) -> str:
    if not identifier.replace("_", "").isalnum():
        raise ValueError(f"Unexpected database identifier: {identifier!r}")
    return '"' + identifier.replace('"', '""') + '"'


def _backup_source(source: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = source.with_name(f"{source.stem}.backup-{stamp}{source.suffix or '.sqlite'}")
    with sqlite3.connect(source) as original, sqlite3.connect(backup) as copy:
        original.backup(copy)
    return backup


def _source_table_columns(source, table):
    return [row[1] for row in source.execute(f"PRAGMA table_info({_quote(table)})").fetchall()]


def migrate(source_path: str | Path) -> dict:
    if not is_postgres_enabled():
        raise RuntimeError("Set DATABASE_URL to the new Supabase PostgreSQL session-pooler connection string first.")
    source_path = Path(source_path).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"SQLite database not found: {source_path}")

    backup_path = _backup_source(source_path)
    source = sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    target = None
    try:
        source_tables = {
            row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        missing = {"courses", "users", "questions", "progress"} - source_tables
        if missing:
            raise RuntimeError("The source SQLite database is missing required tables: " + ", ".join(sorted(missing)))

        initialize_database(seed_reference_data=False)
        target = connect_db()
        cursor = target.cursor()
        occupied = []
        for table in DESTINATION_MUST_BE_EMPTY:
            cursor.execute(f"SELECT COUNT(*) AS count FROM {_quote(table)}")
            if cursor.fetchone()["count"]:
                occupied.append(table)
        if occupied:
            raise RuntimeError(
                "The Supabase destination already has user data in " + ", ".join(occupied)
                + ". Use a new empty Supabase project to avoid overwriting or mixing records."
            )

        copied_counts = {}
        for table in TABLES_IN_ORDER:
            if table not in source_tables:
                copied_counts[table] = 0
                continue

            source_columns = _source_table_columns(source, table)
            cursor.execute(f"SELECT * FROM {_quote(table)} LIMIT 0")
            target_columns = [column.name for column in cursor.description]
            mapped = []
            for name in source_columns:
                destination_name = "password" if table == "users" and name == "password_hash" and "password" not in source_columns else name
                if destination_name in target_columns:
                    mapped.append((name, destination_name))
            if table == "users" and not any(dest == "password" for _, dest in mapped):
                raise RuntimeError("The source users table has no supported password-hash column.")
            if not mapped:
                copied_counts[table] = 0
                continue

            target_names = [destination for _, destination in mapped]
            quoted_columns = ", ".join(_quote(name) for name in target_names)
            placeholders = ", ".join(["%s"] * len(target_names))
            if table in UPSERT_REFERENCE_TABLES:
                mutable = [name for name in target_names if name != "id"]
                conflict = "DO UPDATE SET " + ", ".join(
                    f"{_quote(name)} = EXCLUDED.{_quote(name)}" for name in mutable
                ) if mutable else "DO NOTHING"
                statement = (
                    f"INSERT INTO {_quote(table)} ({quoted_columns}) VALUES ({placeholders}) "
                    f"ON CONFLICT (id) {conflict}"
                )
            else:
                statement = (
                    f"INSERT INTO {_quote(table)} ({quoted_columns}) VALUES ({placeholders}) "
                    "ON CONFLICT DO NOTHING"
                )

            count = 0
            rows = source.execute(f"SELECT * FROM {_quote(table)}")
            while batch := rows.fetchmany(500):
                values = [tuple(row[source_name] for source_name, _ in mapped) for row in batch]
                cursor.executemany(statement, values)
                count += len(batch)
            copied_counts[table] = count

        for table in ("users", "progress", "bounty_records"):
            cursor.execute(
                "SELECT setval(pg_get_serial_sequence(%s, 'id'), "
                f"GREATEST(COALESCE(MAX(id), 1), 1), COUNT(*) > 0) FROM {_quote(table)}",
                (table,),
            )

        for table in TABLES_IN_ORDER:
            if table not in source_tables:
                continue
            source_count = source.execute(f"SELECT COUNT(*) FROM {_quote(table)}").fetchone()[0]
            cursor.execute(f"SELECT COUNT(*) AS count FROM {_quote(table)}")
            target_count = cursor.fetchone()["count"]
            if target_count != source_count:
                raise RuntimeError(
                    f"Record-count check failed for {table}: source={source_count}, destination={target_count}."
                )

        cursor.execute(
            "INSERT INTO schema_migrations (version) VALUES (%s) ON CONFLICT (version) DO NOTHING",
            ("002_seed_reference_data",),
        )

        cursor.execute("""SELECT COUNT(*) AS count FROM progress p
            LEFT JOIN users u ON u.id = p.user_id
            LEFT JOIN courses c ON c.id = p.course_id
            WHERE u.id IS NULL OR c.id IS NULL""")
        if cursor.fetchone()["count"]:
            raise RuntimeError("Relationship verification found progress rows without a user or course.")

        target.commit()
        return {"backup": str(backup_path), "copied": copied_counts}
    except Exception:
        if target is not None:
            target.rollback()
        raise
    finally:
        source.close()
        if target is not None:
            target.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sqlite_database", help="Path to the existing bountycoders.db file")
    args = parser.parse_args()
    result = migrate(args.sqlite_database)
    print(f"SQLite backup created at: {result['backup']}")
    for table, count in result["copied"].items():
        print(f"{table}: {count} source rows copied")
