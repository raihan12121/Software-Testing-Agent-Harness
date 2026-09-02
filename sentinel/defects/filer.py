"""Automated Defect Filing for confirmed failures.

Adheres strictly to:
- PRD FR-19 (Auto defect filing)
- rules.md R-REPORT-1 (Every defect must have reproducible steps and linked artifacts)
- memory.md §3 (defects table schema and fingerprint deduplication)
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sentinel.core.logging import logger
from sentinel.core.schemas import Report, TestCase, Verdict
from sentinel.memory.store import MemoryStore


class DefectFiler:
    """Formats reproducible defect reports and files them to GitHub Issues or issue tracker."""

    def __init__(self, memory_store: MemoryStore | None = None) -> None:
        self.memory_store = memory_store or MemoryStore()

    @staticmethod
    def generate_fingerprint(verdict: Verdict) -> str:
        """Compute stable hash of failure reason and assertion to deduplicate defects."""
        seed = f"{verdict.test_id}:{verdict.status}:{verdict.reasoning[:120]}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]

    def format_defect_body(
        self,
        test_case: TestCase,
        verdict: Verdict,
        report: Report,
    ) -> str:
        """Format markdown defect body adhering to R-REPORT-1."""
        repro_lines = []
        for i, step in enumerate(test_case.steps, start=1):
            body_info = f" with payload `{step.body}`" if step.body else ""
            repro_lines.append(f"{i}. Execute `{step.action}` on `{step.path}`{body_info}")

        artifacts_lines = []
        for a in test_case.expected.assertions:
            artifacts_lines.append(f"- Expected: `{a}`")

        body = f"""## Defect Report: {test_case.title}

### 1. Environment & Target (R-REPORT-1)
- **Environment:** `{report.environment}`
- **Target Type:** `{report.target_type}`
- **Run ID:** `{report.run_id}`
- **Test ID:** `{test_case.id}`
- **Timestamp:** `{report.started_at}`

### 2. Steps to Reproduce
{chr(10).join(repro_lines)}

### 3. Expected vs. Actual Result
- **Expected Assertions:**
{chr(10).join(artifacts_lines) if artifacts_lines else "- Expected criteria satisfied"}
- **Actual Status:** `{verdict.status}`
- **Failure Reasoning:**
> {verdict.reasoning}

### 4. Fingerprint & Deduplication
- **Defect Fingerprint:** `{self.generate_fingerprint(verdict)}`
"""
        return body

    def file_defect(
        self,
        test_case: TestCase,
        verdict: Verdict,
        report: Report,
        issue_client: Any | None = None,
    ) -> dict[str, Any] | None:
        """File defect if not already logged in defects table (deduplication)."""
        fingerprint = self.generate_fingerprint(verdict)
        defect_record_id = f"DEF-{fingerprint}"

        # Check if defect already exists in memory store
        with self.memory_store.connection() as conn:
            existing = conn.execute(
                "SELECT defect_id, tracker_url FROM defects WHERE defect_id = ?",
                (defect_record_id,),
            ).fetchone()

            if existing:
                logger.info(f"Defect {defect_record_id} already filed (URL: {existing['tracker_url']}). Skipping duplicate.")
                return {
                    "id": existing["defect_id"],
                    "defect_id": existing["defect_id"],
                    "github_issue_url": existing["tracker_url"],
                    "fingerprint": fingerprint,
                }

            # Generate structured title and markdown description
            title = f"[Bug] [{test_case.target_type.upper()}] {test_case.title}"
            body = self.format_defect_body(test_case, verdict, report)

            # File via issue_client or generate simulated tracker issue URL
            if issue_client and hasattr(issue_client, "create_issue"):
                issue_res = issue_client.create_issue(title=title, body=body)
                issue_url = issue_res.get("html_url")
            else:
                defect_num = int(datetime.now(timezone.utc).timestamp())
                issue_url = f"https://github.com/mock-org/repo/issues/{defect_num}"

            # Persist in SQLite memory store (memory.md §3)
            module_name = test_case.source_context.split("://")[-1].split("/")[0] if test_case.source_context else "general"
            conn.execute(
                """
                INSERT INTO defects (
                    defect_id, project_id, title, severity, root_cause_tags,
                    linked_test_ids, tracker_url, status, first_seen_run_id, module
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    defect_record_id,
                    report.project_id,
                    title,
                    "high",
                    json.dumps(["auto_detected", test_case.target_type]),
                    json.dumps([test_case.id]),
                    issue_url,
                    "filed",
                    report.run_id,
                    module_name,
                ),
            )
            conn.commit()

            logger.info(f"Filed new defect {defect_record_id} for test {test_case.id}: {issue_url}")
            return {
                "defect_id": defect_record_id,
                "id": defect_record_id,
                "fingerprint": fingerprint,
                "title": title,
                "github_issue_url": issue_url,
                "body": body,
            }
