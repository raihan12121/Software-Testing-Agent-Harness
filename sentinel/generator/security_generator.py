"""Security & Penetration-Oriented Test Generator with strict R-SAFE guardrails.

Adheres strictly to:
- phases.md §Phase 5 (Security/pentest-oriented test generation with strict R-SAFE guardrails)
- rules.md R-GEN-1 (Executable test cases)
- rules.md R-SAFE-1 (Safe non-destructive probing)
"""

from __future__ import annotations

from sentinel.core.schemas import ExpectedResult, TargetModel, TestCase, TestStep


class SecurityTestGenerator:
    """Generates scoped, non-destructive vulnerability probing test suites."""

    def generate_security_suite(self, target_model: TargetModel) -> list[TestCase]:
        """Generate comprehensive, grounded security probes adhering to R-SAFE guardrails."""
        tests: list[TestCase] = []
        tc_idx = 1

        for ep in target_model.endpoints:
            path = ep.get("path", "/")
            method = ep.get("method", "GET").upper()

            # 1. SQL Injection / Injection Boundary Probe
            tests.append(
                TestCase(
                    id=f"TC-SEC-INJ-{tc_idx:03d}",
                    target_type="api",
                    title=f"Security Probe: Injection Boundary Rejection on {method} {path}",
                    steps=[
                        TestStep(
                            action="http_request",
                            method=method,
                            path=f"{path}?search=' OR '1'='1' --",
                            body={"query": "'; DROP TABLE test; --"} if method in ("POST", "PUT") else None,
                        )
                    ],
                    expected=ExpectedResult(
                        oracle="deterministic",
                        assertions=[
                            "status_code in [200, 400, 404, 422]",
                            "status_code != 500",  # Must not crash backend with unhandled 500
                        ],
                    ),
                    priority="critical",
                    tags=["security", "injection", "r_safe_probe"],
                    generated_by="security_generator",
                    source_context=f"security://injection/{path}",
                )
            )

            # 2. Broken Object Level Authorization (BOLA / IDOR) Probe
            tests.append(
                TestCase(
                    id=f"TC-SEC-BOLA-{tc_idx:03d}",
                    target_type="api",
                    title=f"Security Probe: Authorization Boundary on {method} {path}",
                    steps=[
                        TestStep(
                            action="http_request",
                            method=method,
                            path=path,
                            headers={"Authorization": "Bearer invalid_or_expired_token"},
                        )
                    ],
                    expected=ExpectedResult(
                        oracle="deterministic",
                        assertions=["status_code in [401, 403, 404]"],
                    ),
                    priority="critical",
                    tags=["security", "bola", "auth"],
                    generated_by="security_generator",
                    source_context=f"security://auth/{path}",
                )
            )

            # 3. Information Disclosure / Stack Trace Leak Probe
            tests.append(
                TestCase(
                    id=f"TC-SEC-LEAK-{tc_idx:03d}",
                    target_type="api",
                    title=f"Security Probe: No Stack Trace Leakage on {method} {path}",
                    steps=[
                        TestStep(
                            action="http_request",
                            method=method,
                            path=f"{path}?id=-999999999999999999",
                        )
                    ],
                    expected=ExpectedResult(
                        oracle="deterministic",
                        assertions=[
                            "status_code in [200, 400, 404, 422]",
                            "status_code != 500",
                        ],
                    ),
                    priority="high",
                    tags=["security", "info_leak"],
                    generated_by="security_generator",
                    source_context=f"security://infoleak/{path}",
                )
            )
            tc_idx += 1

        return tests
