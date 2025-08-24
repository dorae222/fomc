"""Simple migration manager for SQLite.

Provides a minimal MigrationManager used by setup_db.py. It ensures a
schema_migrations table exists and can be extended with real migrations later.
"""
from __future__ import annotations

import sqlite3
import logging
from typing import List, Tuple
import config

logger = logging.getLogger(__name__)


class MigrationManager:
    """Minimal migration manager.

    - Ensures a schema_migrations table exists.
    - Applies migrations listed in `self.migrations` if not yet applied.
    """

    def __init__(self, db_path=None):
        self.db_path = db_path or config.DATABASE_PATH
        # List of migrations as (version, sql_statements)
        # Keep empty initially; structure is ready for future changes.
        self.migrations: List[Tuple[str, List[str]]] = []

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_table(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    def _get_applied_versions(self, conn: sqlite3.Connection) -> set:
        cur = conn.execute("SELECT version FROM schema_migrations")
        return {row[0] for row in cur.fetchall()}

    def run_migrations(self) -> bool:
        """Apply any pending migrations. Returns True on success."""
        try:
            with self._connect() as conn:
                self._ensure_table(conn)
                applied = self._get_applied_versions(conn)

                for version, statements in self.migrations:
                    if version in applied:
                        continue
                    logger.info(f"Applying migration {version}...")
                    try:
                        conn.execute("BEGIN")
                        for stmt in statements:
                            conn.execute(stmt)
                        conn.execute(
                            "INSERT INTO schema_migrations(version) VALUES (?)",
                            (version,),
                        )
                        conn.commit()
                        logger.info(f"Migration {version} applied")
                    except Exception as e:
                        conn.rollback()
                        logger.error(f"Migration {version} failed: {e}")
                        return False

            # Nothing or all applied successfully
            if not self.migrations:
                logger.info("No database migrations to apply")
            return True
        except Exception as e:
            logger.error(f"Migration manager error: {e}")
            return False
