"""Dual-Grounded Action Resolver.

Bridges visual perception (Set-of-Marks) and semantic structure (DOM/A11y selectors),
ensuring zero coordinate drift and enabling self-healing selector fallback.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any

from sentinel.computer_use.som import InteractiveElement


@dataclass
class GroundedAction:
    """An executable, grounded action resolved with both selector and coordinate anchors."""
    action_type: str  # click, fill, press, hover, scroll, navigate, assert, wait
    target_index: int | None = None
    selector: str | None = None
    x: int | None = None
    y: int | None = None
    value: Any = None
    expected: str | None = None
    reasoning: str = ""
    is_self_healed: bool = False
    original_target: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "target_index": self.target_index,
            "selector": self.selector,
            "coordinates": {"x": self.x, "y": self.y} if self.x is not None else None,
            "value": self.value,
            "expected": self.expected,
            "reasoning": self.reasoning,
            "is_self_healed": self.is_self_healed,
            "original_target": self.original_target,
        }


class ActionResolver:
    """Resolves and grounds multimodal agent intents to concrete UI interactions."""

    @classmethod
    def resolve(
        cls,
        raw_action: dict[str, Any],
        elements: list[InteractiveElement],
    ) -> GroundedAction:
        """Resolve a raw agent action against current viewport elements."""
        action_type = str(raw_action.get("type") or raw_action.get("action") or "click").lower()
        target_raw = raw_action.get("target") or raw_action.get("selector") or raw_action.get("element")
        value = raw_action.get("value") or raw_action.get("text")
        expected = raw_action.get("expected") or raw_action.get("assertion")
        reasoning = raw_action.get("reasoning", "")
        raw_x = raw_action.get("x")
        raw_y = raw_action.get("y")

        # 1. Navigation / Global Actions (no element target required)
        if action_type in ("navigate", "goto", "open"):
            url = str(value or target_raw or raw_action.get("url", ""))
            return GroundedAction(
                action_type="navigate",
                value=url,
                reasoning=reasoning,
                original_target=url,
            )

        if action_type in ("wait", "sleep"):
            duration = float(value or 1.0)
            return GroundedAction(
                action_type="wait",
                value=duration,
                reasoning=reasoning,
            )

        if action_type == "assert":
            return GroundedAction(
                action_type="assert",
                expected=str(expected or value or ""),
                reasoning=reasoning,
            )

        # 2. Target Resolution via Badge Index (e.g. target="1" or target=1)
        matched_element: InteractiveElement | None = None
        target_str = str(target_raw or "").strip()

        if target_str.isdigit():
            idx = int(target_str)
            for el in elements:
                if el.index == idx:
                    matched_element = el
                    break

        # 3. Target Resolution via Selector / ID / Text Search
        if not matched_element and target_str:
            # Exact selector match
            for el in elements:
                if el.selector == target_str or el.element_id == target_str:
                    matched_element = el
                    break

        # 4. Self-Healing Fallback (Fuzzy matching on text, role, or ID if broken selector)
        is_self_healed = False
        if not matched_element and target_str and not (raw_x is not None and raw_y is not None):
            best_el = None
            highest_ratio = 0.0

            for el in elements:
                # Compare against text, selector, and id
                r1 = difflib.SequenceMatcher(None, target_str.lower(), el.text.lower()).ratio()
                r2 = difflib.SequenceMatcher(None, target_str.lower(), el.element_id.lower()).ratio()
                r3 = difflib.SequenceMatcher(None, target_str.lower(), el.selector.lower()).ratio()
                score = max(r1, r2, r3)
                if score > highest_ratio and score >= 0.5:
                    highest_ratio = score
                    best_el = el

            if best_el:
                matched_element = best_el
                is_self_healed = True

        # 5. Build Final Grounded Action
        if matched_element:
            cx, cy = matched_element.center_point
            return GroundedAction(
                action_type=action_type,
                target_index=matched_element.index,
                selector=matched_element.selector,
                x=cx,
                y=cy,
                value=value,
                expected=expected,
                reasoning=reasoning,
                is_self_healed=is_self_healed,
                original_target=target_str,
                metadata={"element_info": matched_element.to_dict()},
            )

        # 6. Fallback to Raw Coordinates
        if raw_x is not None and raw_y is not None:
            return GroundedAction(
                action_type=action_type,
                x=int(raw_x),
                y=int(raw_y),
                value=value,
                expected=expected,
                reasoning=reasoning,
                original_target=f"coords({raw_x},{raw_y})",
            )

        # 7. Fallback to raw selector execution
        return GroundedAction(
            action_type=action_type,
            selector=target_str if target_str else None,
            value=value,
            expected=expected,
            reasoning=reasoning,
            original_target=target_str,
        )
