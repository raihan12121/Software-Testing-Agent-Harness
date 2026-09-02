"""Deterministic assertion evaluation engine.

Adheres to:
- TRD.md §3.3 & §5 (Deterministic where it matters)
- rules.md R-ORACLE-1 (Deterministic first)
"""

from __future__ import annotations

import ast
import operator
from typing import Any

from sentinel.core.schemas import AssertionResult, Observation, TestCase, Verdict
from sentinel.oracle.base import Oracle, register_oracle


class DeterministicOracle(Oracle):
    """Evaluates deterministic expressions against observation raw results."""

    OPERATORS = {
        ast.Eq: operator.eq,
        ast.NotEq: operator.ne,
        ast.Lt: operator.lt,
        ast.LtE: operator.le,
        ast.Gt: operator.gt,
        ast.GtE: operator.ge,
        ast.In: lambda a, b: a in b,
        ast.NotIn: lambda a, b: a not in b,
        ast.Is: operator.is_,
        ast.IsNot: operator.is_not,
    }

    def evaluate(self, test_case: TestCase, observation: Observation) -> Verdict:
        """Evaluate all assertions in test_case.expected against observation."""
        # If observation itself contains an execution error, verdict is 'error'
        if observation.error:
            return Verdict(
                test_id=test_case.id,
                status="error",
                oracle_used="deterministic",
                reasoning=f"Execution error encountered: {observation.error}",
                duration_ms=observation.duration_ms,
            )

        assertions = test_case.expected.assertions
        if not assertions:
            # If no assertions provided, pass if no error occurred
            return Verdict(
                test_id=test_case.id,
                status="pass",
                oracle_used="deterministic",
                reasoning="No assertions specified; execution completed without error.",
                duration_ms=observation.duration_ms,
            )

        context = self._build_evaluation_context(observation.raw_result)
        results: list[AssertionResult] = []
        all_passed = True

        for expr in assertions:
            res = self._evaluate_assertion(expr, context)
            results.append(res)
            if not res.passed:
                all_passed = False

        status = "pass" if all_passed else "fail"
        reasoning = (
            f"All {len(assertions)} assertions passed."
            if all_passed
            else f"{sum(1 for r in results if not r.passed)} of {len(assertions)} assertions failed."
        )

        return Verdict(
            test_id=test_case.id,
            status=status,
            oracle_used="deterministic",
            reasoning=reasoning,
            assertions_result=results,
            duration_ms=observation.duration_ms,
        )

    def _build_evaluation_context(self, raw_result: dict[str, Any]) -> dict[str, Any]:
        """Wrap dicts to allow dot-notation access."""

        class DotDict(dict):
            def __getattr__(self, name: str) -> Any:
                if name in self:
                    val = self[name]
                    if isinstance(val, dict) and not isinstance(val, DotDict):
                        return DotDict(val)
                    return val
                return None

        context: dict[str, Any] = {}
        for k, v in raw_result.items():
            if isinstance(v, dict):
                context[k] = DotDict(v)
            else:
                context[k] = v
        return context

    def _evaluate_assertion(self, expr_str: str, context: dict[str, Any]) -> AssertionResult:
        """Safely parse and evaluate an assertion expression."""
        try:
            tree = ast.parse(expr_str.strip(), mode="eval")
            passed, actual_val = self._eval_node(tree.body, context)
            return AssertionResult(
                assertion=expr_str,
                actual=actual_val,
                passed=bool(passed),
                message=None if passed else f"Assertion failed: expected '{expr_str}', got actual: {actual_val}",
            )
        except Exception as err:
            return AssertionResult(
                assertion=expr_str,
                actual=None,
                passed=False,
                message=f"Evaluation error on '{expr_str}': {err}",
            )

    def _eval_node(self, node: ast.AST, context: dict[str, Any]) -> tuple[Any, Any]:
        """Recursive AST evaluator for safe expressions."""
        if isinstance(node, ast.Compare):
            left_val, _ = self._eval_node(node.left, context)
            actual_left = left_val
            for op, comparator in zip(node.ops, node.comparators):
                comp_val, _ = self._eval_node(comparator, context)
                op_func = self.OPERATORS.get(type(op))
                if not op_func:
                    raise NotImplementedError(f"Unsupported operator: {type(op)}")
                if not op_func(left_val, comp_val):
                    return False, actual_left
                left_val = comp_val
            return True, actual_left

        if isinstance(node, ast.Name):
            val = context.get(node.id)
            return val, val

        if isinstance(node, ast.Attribute):
            obj_val, _ = self._eval_node(node.value, context)
            val = getattr(obj_val, node.attr, None)
            return val, val

        if isinstance(node, ast.Subscript):
            obj_val, _ = self._eval_node(node.value, context)
            slice_val, _ = self._eval_node(node.slice, context)
            try:
                val = obj_val[slice_val]
            except Exception:
                val = None
            return val, val

        if isinstance(node, ast.Constant):
            return node.value, node.value

        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            val, actual = self._eval_node(node.operand, context)
            return not bool(val), actual

        raise NotImplementedError(f"Unsupported AST node in assertion: {type(node)}")


# Register deterministic oracle
register_oracle("deterministic", DeterministicOracle)
