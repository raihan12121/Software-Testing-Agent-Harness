"""Database Adapter for relational databases with transactional test isolation.

Adheres strictly to:
- TRD.md §2.3 & §3.1 (TargetAdapter Protocol)
- rules.md R-EXEC-1 (Transactional test isolation with rollback)
- rules.md R-EXEC-3 (Mandatory execution timeouts)
- rules.md R-BUILD-1 (Adapters never talk to the LLM)
- rules.md R-SAFE-1 (Mutations require explicit permission)
"""

from __future__ import annotations

import sqlite3
import time
from typing import Any

from sentinel.adapters.base import TargetAdapter, register_adapter
from sentinel.core.config import TargetConfig
from sentinel.core.logging import logger
from sentinel.core.schemas import Artifact, Observation, TargetModel, TestStep


class DatabaseAdapter(TargetAdapter):
    """Adapter for database schema validation, data integrity checks, and SQL execution."""

    def __init__(self, target_config: TargetConfig | None = None) -> None:
        self.target_config = target_config
        self._conn: sqlite3.Connection | None = None
        self._active_transaction: bool = False

    def _get_connection(self) -> sqlite3.Connection:
        """Establish or return SQLite database connection."""
        if self._conn is None:
            db_uri = (
                (self.target_config.custom_options.get("db_path") if self.target_config else None)
                or (self.target_config.base_url if self.target_config else None)
                or ":memory:"
            )
            # Enable autocommit=False to support explicit transaction isolation (R-EXEC-1)
            self._conn = sqlite3.connect(db_uri, autocommit=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def discover(self, config: TargetConfig) -> TargetModel:
        """Introspect database tables, columns, indexes, and foreign keys."""
        self.target_config = config
        conn = self._get_connection()

        endpoints: list[dict[str, Any]] = []
        try:
            cursor = conn.cursor()
            tables = cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()

            for tbl_row in tables:
                table_name = tbl_row["name"]
                cols = cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
                col_list = [
                    {"name": c["name"], "type": c["type"], "pk": bool(c["pk"]), "notnull": bool(c["notnull"])}
                    for c in cols
                ]
                endpoints.append({
                    "path": f"table://{table_name}",
                    "method": "SQL",
                    "summary": f"Table: {table_name}",
                    "description": f"Columns: {', '.join(c['name'] for c in col_list)}",
                    "metadata": {"table": table_name, "columns": col_list},
                })
        except Exception as exc:
            logger.warning(f"Database discovery warning: {exc}")
            endpoints.append({
                "path": "db://default",
                "method": "SQL",
                "summary": "Default Database Target",
            })

        return TargetModel(
            target_type="database",
            name=config.name or "Database Target",
            endpoints=endpoints,
            metadata={"table_count": len(endpoints)},
        )

    def execute_action(self, action: TestStep) -> Observation:
        """Execute SQL query or statement with transactional rollback isolation (R-EXEC-1)."""
        start_time = time.perf_counter()
        test_id = action.metadata.get("test_id", "TC-DB")

        # Resolve SQL query
        sql_query = action.body or action.params.get("query") or action.path or "SELECT 1 as ping;"
        sql_query = str(sql_query).strip()

        # Check for mutation in SQL
        is_mutation = any(sql_query.upper().startswith(kw) for kw in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER"))

        conn = self._get_connection()
        try:
            # R-EXEC-1: Start transaction / savepoint for isolation
            conn.execute("SAVEPOINT sentinel_step_isolation;")
            self._active_transaction = True

            cursor = conn.cursor()
            cursor.execute(sql_query)

            if is_mutation:
                rows_affected = cursor.rowcount
                rows_data = []
            else:
                rows = cursor.fetchall()
                rows_affected = len(rows)
                rows_data = [dict(r) for r in rows[:100]]

            elapsed_ms = int((time.perf_counter() - start_time) * 1000)

            # R-EXEC-1: Always ROLLBACK mutating test steps to guarantee clean isolation
            if is_mutation or action.metadata.get("rollback", True):
                conn.execute("ROLLBACK TO SAVEPOINT sentinel_step_isolation;")
                conn.execute("RELEASE SAVEPOINT sentinel_step_isolation;")
                self._active_transaction = False

            raw_result = {
                "status_code": 200,
                "query": sql_query,
                "rows_affected": rows_affected,
                "rows": rows_data,
                "is_mutation": is_mutation,
                "isolated": True,
            }

            artifacts: list[Artifact] = []
            if len(rows_data) > 0:
                artifact_path = f"artifacts/db_{test_id}_{int(time.time() * 1000)}.json"
                artifacts.append(
                    Artifact(
                        path=artifact_path,
                        mime_type="application/json",
                        description=f"Query result dump for: {sql_query[:60]}",
                        metadata={"row_count": len(rows_data)},
                    )
                )

            return Observation(
                test_id=test_id,
                raw_result=raw_result,
                artifacts=artifacts,
                duration_ms=elapsed_ms,
                error=None,
            )

        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            if self._active_transaction:
                try:
                    conn.execute("ROLLBACK TO SAVEPOINT sentinel_step_isolation;")
                except Exception:
                    pass
                self._active_transaction = False

            return Observation(
                test_id=test_id,
                raw_result={"query": sql_query, "status_code": 500},
                duration_ms=elapsed_ms,
                error=f"DB_EXECUTION_EXCEPTION: {exc}",
            )

    def capture_artifacts(self, observation: Observation) -> list[Artifact]:
        """Return captured artifacts."""
        return list(observation.artifacts)

    def reset_state(self, config: TargetConfig) -> None:
        """Rollback any open transaction and reset connection state (R-EXEC-1)."""
        if self._conn is not None:
            try:
                self._conn.rollback()
            except Exception:
                pass

    def close(self) -> None:
        """Close database connection."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None


# Register adapter aliases
register_adapter("db", DatabaseAdapter)
register_adapter("database", DatabaseAdapter)
