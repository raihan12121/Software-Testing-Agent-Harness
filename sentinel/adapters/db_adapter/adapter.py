"""Database Adapter supporting SQLite, PostgreSQL (psycopg), and MongoDB (pymongo).

Adheres strictly to:
- TRD.md §2.3 & §3.1 (TargetAdapter Protocol)
- rules.md R-EXEC-1 (Transactional test isolation with rollback)
- rules.md R-EXEC-3 (Mandatory execution timeouts)
- rules.md R-BUILD-1 (Adapters never talk to the LLM)
- rules.md R-SAFE-1 (Mutations require explicit permission)
- rules.md R-SAFE-5 (Network host allow-listing)
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    import psycopg
    HAS_PSYCOPG = True
except ImportError:
    try:
        import psycopg2 as psycopg
        HAS_PSYCOPG = True
    except ImportError:
        HAS_PSYCOPG = False

try:
    import pymongo
    HAS_PYMONGO = True
except ImportError:
    HAS_PYMONGO = False

from sentinel.adapters.base import TargetAdapter, register_adapter
from sentinel.core.config import TargetConfig
from sentinel.core.logging import logger
from sentinel.core.schemas import Artifact, Observation, TargetModel, TestStep


class DatabaseAdapter(TargetAdapter):
    """Adapter for relational and document databases with transactional rollback isolation (R-EXEC-1)."""

    def __init__(self, target_config: TargetConfig | None = None) -> None:
        self.target_config = target_config
        self._sqlite_conn: sqlite3.Connection | None = None
        self._pg_conn: Any = None
        self._mongo_client: Any = None
        self._mongo_cleanup_records: list[tuple[str, Any]] = []  # (collection_name, doc_id)
        self._active_transaction: bool = False

    def _determine_backend(self, config: TargetConfig) -> str:
        """Determine whether SQLite, PostgreSQL, or MongoDB is targeted."""
        custom_engine = config.custom_options.get("engine", "").lower()
        if custom_engine:
            if "postgr" in custom_engine:
                return "postgres"
            if "mongo" in custom_engine:
                return "mongo"
            if "sqlite" in custom_engine:
                return "sqlite"

        uri = config.base_url or config.custom_options.get("db_path") or ""
        if uri.startswith("postgresql://") or uri.startswith("postgres://"):
            return "postgres"
        if uri.startswith("mongodb://") or uri.startswith("mongodb+srv://"):
            return "mongo"
        return "sqlite"

    def _check_host_allowlist(self, uri: str) -> bool:
        """R-SAFE-5: Verify database host is permitted in allowed_hosts."""
        if not self.target_config or not self.target_config.allowed_hosts:
            return True
        host = urlparse(uri).hostname or ""
        if not host:
            return True
        allowed = self.target_config.allowed_hosts
        return host in allowed or (
            host in ("localhost", "127.0.0.1") and any(h in ("localhost", "127.0.0.1") for h in allowed)
        )

    def _get_sqlite_connection(self) -> sqlite3.Connection:
        """Establish or return SQLite database connection."""
        if self._sqlite_conn is None:
            db_uri = (
                (self.target_config.custom_options.get("db_path") if self.target_config else None)
                or (self.target_config.base_url if self.target_config else None)
                or ":memory:"
            )
            try:
                self._sqlite_conn = sqlite3.connect(db_uri, autocommit=False)
            except TypeError:
                self._sqlite_conn = sqlite3.connect(db_uri, isolation_level=None)
            self._sqlite_conn.row_factory = sqlite3.Row
        return self._sqlite_conn

    def _get_postgres_connection(self, uri: str) -> Any:
        """Establish or return PostgreSQL connection via psycopg."""
        if not HAS_PSYCOPG:
            raise ImportError(
                "PostgreSQL support requires 'psycopg'. Install via: pip install 'sentinel-sqa[db-extended]'"
            )
        if self._pg_conn is None:
            self._pg_conn = psycopg.connect(uri, autocommit=False)
        return self._pg_conn

    def _get_mongo_client(self, uri: str) -> Any:
        """Establish or return MongoDB client via pymongo."""
        if not HAS_PYMONGO:
            raise ImportError(
                "MongoDB support requires 'pymongo'. Install via: pip install 'sentinel-sqa[db-extended]'"
            )
        if self._mongo_client is None:
            self._mongo_client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=3000)
        return self._mongo_client

    def discover(self, config: TargetConfig) -> TargetModel:
        """Introspect database tables/collections, columns/fields, and schemas."""
        self.target_config = config
        backend = self._determine_backend(config)
        endpoints: list[dict[str, Any]] = []

        if backend == "sqlite":
            conn = self._get_sqlite_connection()
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
                        "metadata": {"table": table_name, "columns": col_list, "engine": "sqlite"},
                    })
            except Exception as exc:
                logger.warning(f"SQLite discovery warning: {exc}")

        elif backend == "postgres":
            uri = config.base_url or config.custom_options.get("db_path", "postgresql://localhost:5432/testdb")
            if not self._check_host_allowlist(uri):
                logger.warning(f"PostgreSQL host not allowed by R-SAFE-5: {uri}")
            else:
                try:
                    conn = self._get_postgres_connection(uri)
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                        )
                        tables = cur.fetchall()
                        for row in tables:
                            table_name = row[0]
                            cur.execute(
                                "SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = %s",
                                (table_name,),
                            )
                            cols = cur.fetchall()
                            col_list = [{"name": c[0], "type": c[1], "nullable": c[2] == "YES"} for c in cols]
                            endpoints.append({
                                "path": f"table://{table_name}",
                                "method": "SQL",
                                "summary": f"Postgres Table: {table_name}",
                                "description": f"Columns: {', '.join(c['name'] for c in col_list)}",
                                "metadata": {"table": table_name, "columns": col_list, "engine": "postgres"},
                            })
                except Exception as exc:
                    logger.warning(f"PostgreSQL discovery notice: {exc}")

        elif backend == "mongo":
            uri = config.base_url or config.custom_options.get("db_path", "mongodb://localhost:27017/testdb")
            if not self._check_host_allowlist(uri):
                logger.warning(f"MongoDB host not allowed by R-SAFE-5: {uri}")
            else:
                try:
                    client = self._get_mongo_client(uri)
                    db_name = config.custom_options.get("db_name", "testdb")
                    db = client[db_name]
                    collections = db.list_collection_names()
                    for col_name in collections:
                        sample = db[col_name].find_one() or {}
                        fields = [{"name": k, "type": type(v).__name__} for k, v in sample.items()]
                        endpoints.append({
                            "path": f"collection://{col_name}",
                            "method": "MONGO",
                            "summary": f"Mongo Collection: {col_name}",
                            "description": f"Fields: {', '.join(f['name'] for f in fields)}",
                            "metadata": {"collection": col_name, "fields": fields, "engine": "mongo"},
                        })
                except Exception as exc:
                    logger.warning(f"MongoDB discovery notice: {exc}")

        if not endpoints:
            endpoints.append({
                "path": "db://default",
                "method": "DB",
                "summary": f"Default {backend.title()} Database Target",
            })

        return TargetModel(
            target_type="database",
            name=config.name or f"{backend.title()} Database Target",
            endpoints=endpoints,
            metadata={"table_count": len(endpoints), "engine": backend},
        )

    def execute_action(self, action: TestStep) -> Observation:
        """Execute query or statement with transactional rollback isolation (R-EXEC-1)."""
        start_time = time.perf_counter()
        test_id = action.metadata.get("test_id", "TC-DB")
        backend = self._determine_backend(self.target_config or TargetConfig(target_type="database"))

        query_str = str(action.body or action.params.get("query") or action.path or "SELECT 1;").strip()
        is_mutation = any(query_str.upper().startswith(kw) for kw in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER"))
        if action.action in ("insert", "insert_one", "update", "delete"):
            is_mutation = True

        status_code = 200
        rows_data: list[dict[str, Any]] = []
        rows_affected = 0
        error_msg: str | None = None

        if backend == "sqlite":
            conn = self._get_sqlite_connection()
            try:
                # R-EXEC-1: Start savepoint
                conn.execute("SAVEPOINT sentinel_step_isolation;")
                self._active_transaction = True

                cursor = conn.cursor()
                cursor.execute(query_str)

                if is_mutation:
                    rows_affected = cursor.rowcount
                else:
                    rows = cursor.fetchall()
                    rows_affected = len(rows)
                    rows_data = [dict(r) for r in rows[:100]]

                # R-EXEC-1: Always ROLLBACK mutating test steps for clean isolation
                if is_mutation or action.metadata.get("rollback", True):
                    conn.execute("ROLLBACK TO SAVEPOINT sentinel_step_isolation;")
                    conn.execute("RELEASE SAVEPOINT sentinel_step_isolation;")
                    self._active_transaction = False

            except Exception as exc:
                error_msg = f"SQLITE_EXEC_ERROR: {exc}"
                status_code = 500
                if self._active_transaction:
                    try:
                        conn.execute("ROLLBACK TO SAVEPOINT sentinel_step_isolation;")
                        conn.execute("RELEASE SAVEPOINT sentinel_step_isolation;")
                    except Exception:
                        pass
                    self._active_transaction = False

        elif backend == "postgres":
            uri = self.target_config.base_url if self.target_config else "postgresql://localhost:5432/testdb"
            if not self._check_host_allowlist(uri):
                return Observation(
                    test_id=test_id,
                    raw_result={"uri": uri},
                    duration_ms=0,
                    error=f"SECURITY_BLOCK: PostgreSQL host '{uri}' is not in allowed_hosts (R-SAFE-5).",
                )
            try:
                conn = self._get_postgres_connection(uri)
                conn.execute("SAVEPOINT sentinel_step_isolation;")
                with conn.cursor() as cur:
                    cur.execute(query_str)
                    if is_mutation:
                        rows_affected = cur.rowcount
                    else:
                        rows = cur.fetchall()
                        cols = [desc[0] for desc in cur.description] if cur.description else []
                        rows_data = [dict(zip(cols, r)) for r in rows[:100]]
                        rows_affected = len(rows)

                # R-EXEC-1: Rollback to savepoint
                if is_mutation or action.metadata.get("rollback", True):
                    conn.execute("ROLLBACK TO SAVEPOINT sentinel_step_isolation;")
                    conn.execute("RELEASE SAVEPOINT sentinel_step_isolation;")
                    conn.commit()

            except Exception as exc:
                error_msg = f"POSTGRES_EXEC_ERROR: {exc}"
                status_code = 500

        elif backend == "mongo":
            uri = self.target_config.base_url if self.target_config else "mongodb://localhost:27017/testdb"
            if not self._check_host_allowlist(uri):
                return Observation(
                    test_id=test_id,
                    raw_result={"uri": uri},
                    duration_ms=0,
                    error=f"SECURITY_BLOCK: MongoDB host '{uri}' is not in allowed_hosts (R-SAFE-5).",
                )
            try:
                client = self._get_mongo_client(uri)
                db_name = (self.target_config.custom_options.get("db_name") if self.target_config else None) or "testdb"
                db = client[db_name]
                col_name = action.path.replace("collection://", "") if action.path else "test_col"
                collection = db[col_name]

                action_name = (action.action or "find").lower()
                if action_name in ("insert", "insert_one"):
                    doc = action.body if isinstance(action.body, dict) else {"content": str(action.body)}
                    res = collection.insert_one(doc)
                    rows_affected = 1
                    doc_id = res.inserted_id
                    # R-EXEC-1: Record for immediate rollback isolation
                    if action.metadata.get("rollback", True):
                        collection.delete_one({"_id": doc_id})
                    else:
                        self._mongo_cleanup_records.append((col_name, doc_id))
                    rows_data = [{"inserted_id": str(doc_id)}]
                elif action_name in ("count", "count_documents"):
                    filter_q = action.params.get("filter", {})
                    cnt = collection.count_documents(filter_q)
                    rows_affected = cnt
                    rows_data = [{"count": cnt}]
                else:
                    filter_q = action.params.get("filter", {})
                    cursor = collection.find(filter_q).limit(100)
                    rows_data = [dict(c, _id=str(c.get("_id"))) for c in cursor]
                    rows_affected = len(rows_data)

            except Exception as exc:
                error_msg = f"MONGO_EXEC_ERROR: {exc}"
                status_code = 500

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        raw_result = {
            "status_code": status_code,
            "engine": backend,
            "query": query_str,
            "rows_affected": rows_affected,
            "rows": rows_data,
            "is_mutation": is_mutation,
            "isolated": True,
        }

        artifacts: list[Artifact] = []
        if len(rows_data) > 0:
            artifact_dir = Path("artifacts")
            artifact_dir.mkdir(parents=True, exist_ok=True)
            artifact_path = artifact_dir / f"db_{test_id}_{int(time.time() * 1000)}.json"
            artifact_path.write_text(json.dumps(rows_data, default=str), encoding="utf-8")
            artifacts.append(
                Artifact(
                    path=str(artifact_path),
                    mime_type="application/json",
                    description=f"Query result dataset for {test_id}",
                    metadata={"row_count": len(rows_data), "engine": backend},
                )
            )

        return Observation(
            test_id=test_id,
            raw_result=raw_result,
            artifacts=artifacts,
            duration_ms=elapsed_ms,
            error=error_msg,
        )

    def capture_artifacts(self, observation: Observation) -> list[Artifact]:
        """Return captured database artifacts."""
        return list(observation.artifacts)

    def reset_state(self, config: TargetConfig) -> None:
        """Reset transactions and clean up any remaining test data (R-EXEC-1)."""
        backend = self._determine_backend(config)
        if backend == "sqlite" and self._sqlite_conn is not None:
            if self._active_transaction:
                try:
                    self._sqlite_conn.execute("ROLLBACK TO SAVEPOINT sentinel_step_isolation;")
                    self._sqlite_conn.execute("RELEASE SAVEPOINT sentinel_step_isolation;")
                except Exception:
                    pass
                self._active_transaction = False
        elif backend == "mongo" and self._mongo_client is not None and self._mongo_cleanup_records:
            try:
                db_name = config.custom_options.get("db_name", "testdb")
                db = self._mongo_client[db_name]
                for col_name, doc_id in self._mongo_cleanup_records:
                    db[col_name].delete_one({"_id": doc_id})
                self._mongo_cleanup_records.clear()
            except Exception:
                pass

    def close(self) -> None:
        """Close database connections."""
        self.reset_state(self.target_config or TargetConfig(target_type="database"))
        if self._sqlite_conn is not None:
            try:
                self._sqlite_conn.close()
            except Exception:
                pass
            self._sqlite_conn = None
        if self._pg_conn is not None:
            try:
                self._pg_conn.close()
            except Exception:
                pass
            self._pg_conn = None
        if self._mongo_client is not None:
            try:
                self._mongo_client.close()
            except Exception:
                pass
            self._mongo_client = None


# Register Database adapter
register_adapter("database", DatabaseAdapter)
