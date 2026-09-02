"""Unit tests for Sentinel Web Dashboard Server."""

from pathlib import Path

import httpx

from sentinel.core.schemas import Report, Verdict
from sentinel.dashboard.server import start_dashboard_server
from sentinel.memory.store import MemoryStore


def test_dashboard_server_endpoints(tmp_path: Path):
    db_file = tmp_path / "dashboard_test.sqlite"
    store = MemoryStore(db_path=db_file)

    # Seed pending review verdict
    v_pending = Verdict(
        test_id="TC-DASH-01",
        status="pending_review",
        oracle_used="llm_judge",
        confidence=0.55,
        reasoning="Ambiguous error message formatting",
    )
    report = Report(
        run_id="run-dash-01",
        project_id="dash-proj",
        target_type="api",
        environment="staging",
        verdicts=[v_pending],
    )
    store.persist_run(report, [])

    # Start dashboard server on high port in non-blocking thread
    port = 9988
    server = start_dashboard_server(port=port, db_path=str(db_file), blocking=False)

    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5.0) as client:
            # 1. Health check
            res_health = client.get("/health")
            assert res_health.status_code == 200
            assert res_health.json()["status"] == "ok"

            # 2. HTML dashboard
            res_html = client.get("/")
            assert res_html.status_code == 200
            assert "Sentinel Team Dashboard" in res_html.text
            assert "TC-DASH-01" in res_html.text

            # 3. API trends
            res_trends = client.get("/api/trends?project_id=dash-proj")
            assert res_trends.status_code == 200
            assert res_trends.json()["total_runs"] == 1

            # 4. API pending reviews
            res_reviews = client.get("/api/reviews")
            assert res_reviews.status_code == 200
            reviews = res_reviews.json()["pending_reviews"]
            assert len(reviews) == 1
            assert reviews[0]["test_id"] == "TC-DASH-01"

            # 5. POST resolve review
            resolve_payload = {
                "test_id": "TC-DASH-01",
                "run_id": "run-dash-01",
                "resolved_status": "pass",
                "resolved_by": "qa_lead",
                "rationale": "Verified behavior is acceptable",
            }
            res_resolve = client.post("/api/reviews/resolve", json=resolve_payload)
            assert res_resolve.status_code == 200
            assert res_resolve.json()["status"] == "success"

            # 6. Verify pending queue is now empty
            res_reviews_after = client.get("/api/reviews")
            assert len(res_reviews_after.json()["pending_reviews"]) == 0

    finally:
        server.shutdown()
        server.server_close()
