"""SQLite Memory Store for Sentinel run history and risk intelligence.

Adheres to:
- memory.md §3 (Storage Schema)
- memory.md §4 (How Memory is used)
- rules.md R-SEC-3 (Redaction before storage)
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sentinel.core.logging import logger
from sentinel.core.redaction import default_redactor
from sentinel.core.schemas import Report, TestCase
from sentinel.memory.models import SCHEMA_SQL


class MemoryStore:
    """Embedded SQLite store for test runs, verdicts, defect history, and risk scoring."""

    def __init__(self, db_path: str | Path = ".sentinel/memory.sqlite") -> None:
        self.db_path = str(db_path)
        self.redactor = default_redactor
        self._mem_conn: sqlite3.Connection | None = None

        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        else:
            self._mem_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._mem_conn.row_factory = sqlite3.Row

        self._init_db()

    @contextmanager
    def connection(self):
        """Yield a database connection and ensure clean closing."""
        if self._mem_conn is not None:
            yield self._mem_conn
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()

    _get_connection = connection

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self.connection() as conn:
            conn.executescript(SCHEMA_SQL)
            conn.commit()

    def persist_run(self, report: Report, test_cases: list[TestCase]) -> None:
        """Persist complete run, test cases, and verdicts with redaction."""
        with self.connection() as conn:
            # 1. Insert run metadata
            config_snapshot = json.dumps(self.redactor.redact(report.summary))
            conn.execute(
                """
                INSERT OR REPLACE INTO runs (
                    run_id, project_id, target_type, environment,
                    started_at, finished_at, config_snapshot,
                    pass_count, fail_count, flaky_count, pending_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.run_id,
                    report.project_id,
                    report.target_type,
                    report.environment,
                    report.started_at.isoformat(),
                    report.finished_at.isoformat(),
                    config_snapshot,
                    report.pass_count,
                    report.fail_count,
                    report.flaky_count,
                    report.pending_count,
                ),
            )

            # 2. Insert test cases
            for tc in test_cases:
                module = tc.source_context.split("#")[0] if tc.source_context else tc.target_type
                clean_schema = self.redactor.redact(tc.model_dump(mode="json"))
                conn.execute(
                    """
                    INSERT OR REPLACE INTO test_cases (
                        test_id, project_id, title, target_type, module,
                        priority, generated_by, source_context, created_at, schema
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tc.id,
                        report.project_id,
                        tc.title,
                        tc.target_type,
                        module,
                        tc.priority,
                        tc.generated_by,
                        tc.source_context,
                        datetime.now(timezone.utc).isoformat(),
                        json.dumps(clean_schema),
                    ),
                )

            # 3. Insert verdicts & update flaky registry
            for v in report.verdicts:
                clean_reasoning = self.redactor.redact_text(v.reasoning or "")
                conn.execute(
                    """
                    INSERT INTO verdicts (
                        run_id, test_id, status, oracle_used,
                        confidence, reasoning, duration_ms, retries
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report.run_id,
                        v.test_id,
                        v.status,
                        v.oracle_used,
                        v.confidence,
                        clean_reasoning,
                        v.duration_ms,
                        v.retries,
                    ),
                )

                # Update flaky test registry if flaky or retried
                if v.status == "flaky" or v.retries > 0:
                    conn.execute(
                        """
                        INSERT INTO flaky_registry (test_id, flake_count, total_runs_observed, first_observed_at)
                        VALUES (?, 1, 1, ?)
                        ON CONFLICT(test_id) DO UPDATE SET
                            flake_count = flake_count + 1,
                            total_runs_observed = total_runs_observed + 1
                        """,
                        (v.test_id, datetime.now(timezone.utc).isoformat()),
                    )

            conn.commit()
            logger.info(f"Persisted run {report.run_id} ({len(test_cases)} tests) to MemoryStore.")

    def get_risk_context(self, project_id: str) -> dict[str, float]:
        """Return computed risk scores per module for the planner."""
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT module, COUNT(*) as fail_count
                FROM test_cases tc
                JOIN verdicts v ON tc.test_id = v.test_id
                WHERE tc.project_id = ? AND v.status IN ('fail', 'error')
                GROUP BY module
                """,
                (project_id,),
            ).fetchall()

            risk_map: dict[str, float] = {}
            for r in rows:
                module = r["module"]
                fails = r["fail_count"]
                risk_map[module] = min(1.0, 0.1 * fails)
            return risk_map

    def get_flaky_test_ids(self) -> list[str]:
        """Return list of known flaky test IDs."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT test_id FROM flaky_registry WHERE flake_count >= 1"
            ).fetchall()
            return [r["test_id"] for r in rows]

    def get_pending_reviews(self, run_id: str | None = None) -> list[dict[str, Any]]:
        """Query verdicts requiring human review (R-ORACLE-2)."""
        with self.connection() as conn:
            if run_id:
                query = """
                SELECT v.id as verdict_id, v.run_id, v.test_id, v.status, v.confidence, v.reasoning,
                       tc.title, tc.module, tc.source_context, tc.schema
                FROM verdicts v
                JOIN test_cases tc ON v.test_id = tc.test_id
                WHERE v.status = 'pending_review' AND v.run_id = ?
                """
                rows = conn.execute(query, (run_id,)).fetchall()
            else:
                query = """
                SELECT v.id as verdict_id, v.run_id, v.test_id, v.status, v.confidence, v.reasoning,
                       tc.title, tc.module, tc.source_context, tc.schema
                FROM verdicts v
                JOIN test_cases tc ON v.test_id = tc.test_id
                WHERE v.status = 'pending_review'
                ORDER BY v.id DESC
                """
                rows = conn.execute(query).fetchall()

            return [dict(r) for r in rows]

    def record_human_resolution(
        self,
        test_id: str,
        run_id: str,
        original_status: str,
        resolved_status: str,
        resolved_by: str,
        rationale: str,
    ) -> None:
        """Record human review resolution and maintain audit trail (R-ORACLE-5)."""
        with self.connection() as conn:
            # 1. Insert into human_review_resolutions audit log
            conn.execute(
                """
                INSERT INTO human_review_resolutions (
                    test_id, run_id, original_status, resolved_status,
                    resolved_by, rationale, resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    test_id,
                    run_id,
                    original_status,
                    resolved_status,
                    resolved_by,
                    self.redactor.redact_text(rationale),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

            # 2. Update verdict in verdicts table
            conn.execute(
                """
                UPDATE verdicts
                SET status = ?
                WHERE test_id = ? AND run_id = ? AND status = 'pending_review'
                """,
                (resolved_status, test_id, run_id),
            )
            conn.commit()
            logger.info(
                f"Human resolution recorded for {test_id} in {run_id}: "
                f"{original_status} -> {resolved_status} by {resolved_by} (R-ORACLE-5)."
            )
