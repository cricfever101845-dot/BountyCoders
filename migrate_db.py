"""Apply the versioned, non-destructive BountyCoders database migrations."""

import logging
import os
import time

from database import initialize_database


def migrate():
    attempts = max(1, min(int(os.environ.get("MIGRATION_ATTEMPTS", "4")), 6))
    for attempt in range(attempts):
        try:
            initialize_database()
            logging.getLogger(__name__).info("Database schema is ready; existing records were preserved.")
            return
        except Exception as exc:
            try:
                import psycopg2
                temporary_database_error = isinstance(exc, psycopg2.OperationalError)
            except ImportError:
                temporary_database_error = False
            if not temporary_database_error or attempt + 1 == attempts:
                raise
            delay = min(2 ** attempt, 8)
            logging.getLogger(__name__).warning("Database not reachable yet; retrying migration in %s seconds.", delay)
            time.sleep(delay)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    migrate()
