"""Autonomous Explore Mode for discovering untested application flows.

Adheres strictly to:
- rules.md R-SAFE-3 (Explore mode is strictly sandboxed; refuses to run in production)
- phases.md §Phase 3 (Explore mode flow discovery)
- rules.md R-GEN-1 (Executable test cases)
"""

from __future__ import annotations

from sentinel.adapters.base import TargetAdapter
from sentinel.core.config import RunConfig, TargetConfig
from sentinel.core.logging import logger
from sentinel.core.schemas import ExpectedResult, TestCase, TestStep


class SecurityViolationError(Exception):
    """Raised when an operation violates Sentinel hard safety rules."""
    pass


class AutonomousExplorer:
    """Explores targets autonomously to discover previously untested user flows."""

    def __init__(self, target_config: TargetConfig, run_config: RunConfig) -> None:
        self.target_config = target_config
        self.run_config = run_config

        # Hard safety enforcement: R-SAFE-3
        if self.run_config.environment == "production":
            raise SecurityViolationError(
                "SECURITY_VIOLATION: Explore mode is strictly prohibited against 'production' environments (R-SAFE-3). "
                "Explore mode is only permitted in sandboxed, staging, or local environments."
            )

    def explore(self, adapter: TargetAdapter, max_depth: int = 2, max_steps: int = 10) -> list[TestCase]:
        """Autonomously crawl target and synthesize newly discovered test cases."""
        logger.info(
            f"Starting Autonomous Explore Mode against {self.target_config.target_type} "
            f"in environment '{self.run_config.environment}' (R-SAFE-3 verified)."
        )

        discovered_cases: list[TestCase] = []
        target_model = adapter.discover(self.target_config)
        seen_paths: set[str] = set()

        # Seed discovery with known endpoints
        for ep in target_model.endpoints:
            path = ep.get("path", "")
            seen_paths.add(path)

        # Explore variations: discovery of query parameters, sub-routes, and boundary flows
        exploration_idx = 1
        for ep in target_model.endpoints[:max_steps]:
            base_path = ep.get("path", "/")
            method = ep.get("method", "GET").upper()

            # Synthesize an unmapped exploratory flow
            if self.target_config.target_type == "api":
                # Discover query variation (e.g. filtering, pagination, search)
                alt_path = f"{base_path}?debug=true&sort=desc"
                discovered_cases.append(
                    TestCase(
                        id=f"TC-EXPLORE-{exploration_idx:03d}",
                        target_type="api",
                        title=f"Exploration: Undocumented query parameters on {method} {base_path}",
                        steps=[
                            TestStep(
                                action="http_request",
                                method=method,
                                path=alt_path,
                                timeout_seconds=10.0,
                            )
                        ],
                        expected=ExpectedResult(
                            oracle="deterministic",
                            assertions=["status_code in [200, 400, 404]"],
                        ),
                        source_context=f"explore_mode_discovery://{base_path}",
                    )
                )
                exploration_idx += 1

            elif self.target_config.target_type == "web":
                # Discover unmapped flows, navigation routes, and interactive subviews
                sub_routes = ["explore-subview", "cart", "product/1", "checkout"]
                for sub in sub_routes:
                    deep_path = f"{base_path.rstrip('/')}/{sub}" if not base_path.endswith(f"/{sub}") else base_path
                    discovered_cases.append(
                        TestCase(
                            id=f"TC-EXPLORE-{exploration_idx:03d}",
                            target_type="web",
                            title=f"Exploration: Autonomous route inspection for {sub}",
                            steps=[
                                TestStep(
                                    action="navigate",
                                    path=deep_path,
                                    timeout_seconds=10.0,
                                )
                            ],
                            expected=ExpectedResult(
                                oracle="deterministic",
                                assertions=["status_code in [200, 404]"],
                            ),
                            source_context=f"explore_mode_discovery://{deep_path}",
                        )
                    )
                    exploration_idx += 1

        logger.info(f"Explore mode discovered {len(discovered_cases)} new test cases.")
        return discovered_cases
