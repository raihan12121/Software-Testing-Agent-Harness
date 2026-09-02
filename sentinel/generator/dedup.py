"""Deduplication and similarity clustering for generated test cases.

Adheres to:
- rules.md R-GEN-4 (No duplicate/near-duplicate bloat, merge with traceability note)
"""

from __future__ import annotations

import hashlib

from sentinel.core.logging import logger
from sentinel.core.schemas import TestCase


class TestDeduplicator:
    """Detects and clusters near-duplicate test cases, merging them with full traceability."""

    @staticmethod
    def _compute_fingerprint(tc: TestCase) -> str:
        """Compute structural fingerprint of test case."""
        step_signatures = []
        for s in tc.steps:
            step_signatures.append(f"{s.action}:{s.method}:{s.path}:{sorted(list(s.params.keys()))}")

        assertions_sig = sorted(tc.expected.assertions)
        combined = f"{tc.target_type}|{'|'.join(step_signatures)}|{'|'.join(assertions_sig)}"
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    def cluster_and_merge(self, test_cases: list[TestCase]) -> list[TestCase]:
        """Cluster duplicate or near-duplicate test cases and merge them."""
        seen: dict[str, TestCase] = {}
        merged_results: list[TestCase] = []

        for tc in test_cases:
            fingerprint = self._compute_fingerprint(tc)
            if fingerprint in seen:
                primary = seen[fingerprint]
                # Merge: record that this test case was combined per R-GEN-4
                logger.info(f"Merging near-duplicate test case {tc.id} into primary {primary.id} (R-GEN-4).")
                if "merged_from" not in primary.tags:
                    primary.tags.append("merged_near_duplicates")
                # Ensure all unique tags are preserved
                for tag in tc.tags:
                    if tag not in primary.tags:
                        primary.tags.append(tag)
            else:
                seen[fingerprint] = tc
                merged_results.append(tc)

        return merged_results

    def deduplicate(self, test_cases: list[TestCase]) -> list[TestCase]:
        """Alias for cluster_and_merge."""
        return self.cluster_and_merge(test_cases)
