"""Collaborative Multi-Agent Test Generation Architecture.

Adheres strictly to:
- architecture.md §5 (Specialized collaborative test generation agents)
- rules.md R-GEN-1 (Executable test cases)
- rules.md R-GEN-4 (Test case deduplication)
- phases.md §Phase 4 (Collaborative multi-agent generation)
"""

from __future__ import annotations

from sentinel.core.logging import logger
from sentinel.core.schemas import ExpectedResult, TargetModel, TestCase, TestStep
from sentinel.generator.dedup import TestDeduplicator


class FunctionalAgent:
    """Specialized Agent focusing on core user flows and happy-path operations."""

    def generate(self, target_model: TargetModel) -> list[TestCase]:
        tests: list[TestCase] = []
        for i, ep in enumerate(target_model.endpoints, start=1):
            path = ep.get("path", "/")
            method = ep.get("method", "GET").upper()
            tests.append(
                TestCase(
                    id=f"TC-FUNC-{i:03d}",
                    target_type=target_model.target_type,  # type: ignore
                    title=f"Core Functional Flow: {method} {path}",
                    steps=[
                        TestStep(
                            action="http_request" if target_model.target_type == "api" else "action",
                            method=method,
                            path=path,
                        )
                    ],
                    expected=ExpectedResult(
                        oracle="deterministic",
                        assertions=["status_code in [200, 201, 204]"],
                    ),
                    priority="high",
                    tags=["functional", "happy_path"],
                    generated_by="multi_agent_functional",
                    source_context=f"multi_agent://functional/{path}",
                )
            )
        return tests


class AdversarialAgent:
    """Specialized Agent focusing on boundary violations, authentication bypass, and edge cases."""

    def generate(self, target_model: TargetModel) -> list[TestCase]:
        tests: list[TestCase] = []
        for i, ep in enumerate(target_model.endpoints, start=1):
            path = ep.get("path", "/")
            method = ep.get("method", "GET").upper()

            # 1. Unauthenticated / Forbidden attempt
            tests.append(
                TestCase(
                    id=f"TC-ADV-AUTH-{i:03d}",
                    target_type=target_model.target_type,  # type: ignore
                    title=f"Adversarial Security: Missing Auth on {method} {path}",
                    steps=[
                        TestStep(
                            action="http_request" if target_model.target_type == "api" else "action",
                            method=method,
                            path=path,
                            headers={},  # Empty credentials
                        )
                    ],
                    expected=ExpectedResult(
                        oracle="deterministic",
                        assertions=["status_code in [401, 403, 404]"],
                    ),
                    priority="critical",
                    tags=["adversarial", "security", "auth"],
                    generated_by="multi_agent_adversarial",
                    source_context=f"multi_agent://adversarial/auth/{path}",
                )
            )

            # 2. Boundary / Malformed payload attempt
            tests.append(
                TestCase(
                    id=f"TC-ADV-BOUND-{i:03d}",
                    target_type=target_model.target_type,  # type: ignore
                    title=f"Adversarial Boundary: Overflow/Injection on {method} {path}",
                    steps=[
                        TestStep(
                            action="http_request" if target_model.target_type == "api" else "action",
                            method=method,
                            path=path,
                            body={"overflow": "A" * 5000, "injection": "' OR 1=1 --"},
                        )
                    ],
                    expected=ExpectedResult(
                        oracle="deterministic",
                        assertions=["status_code in [400, 422, 404]"],
                    ),
                    priority="high",
                    tags=["adversarial", "boundary", "injection"],
                    generated_by="multi_agent_adversarial",
                    source_context=f"multi_agent://adversarial/boundary/{path}",
                )
            )
        return tests


class MultiAgentGenerator:
    """Coordinates collaborative multi-agent test generation and reconciliation (architecture.md §5)."""

    def __init__(self) -> None:
        self.functional_agent = FunctionalAgent()
        self.adversarial_agent = AdversarialAgent()
        self.deduplicator = TestDeduplicator()

    def generate_collaborative_suite(self, target_model: TargetModel) -> list[TestCase]:
        """Dispatch generation across specialized agents and reconcile via deduplication."""
        logger.info("Dispatching collaborative generation to FunctionalAgent and AdversarialAgent...")

        func_tests = self.functional_agent.generate(target_model)
        adv_tests = self.adversarial_agent.generate(target_model)

        all_proposals = func_tests + adv_tests
        logger.info(
            f"Multi-Agent generated {len(func_tests)} functional + {len(adv_tests)} adversarial tests "
            f"(Total proposals: {len(all_proposals)})."
        )

        # Reconcile and deduplicate (R-GEN-4)
        reconciled = self.deduplicator.deduplicate(all_proposals)
        logger.info(f"Reconciled multi-agent suite contains {len(reconciled)} unique test cases.")
        return reconciled
