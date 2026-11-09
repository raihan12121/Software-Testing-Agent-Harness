"""Autonomous & Co-Pilot Computer Use QA Agent Loop.

Orchestrates visual perception (Set-of-Marks), streaming chain-of-thought reasoning,
dual-grounded action execution, deep telemetry inspection (network/console), and self-healing.
"""

from __future__ import annotations

import base64
import json
import threading
import time
from typing import Any, Callable

from sentinel.adapters.web_adapter.adapter import WebAdapter
from sentinel.computer_use.dual_grounding import ActionResolver, GroundedAction
from sentinel.computer_use.recorder import ActionRecorder
from sentinel.computer_use.som import InteractiveElement, SetOfMarksAnnotator
from sentinel.core.config import TargetConfig
from sentinel.core.logging import logger
from sentinel.llm.provider import LLMProvider, get_llm_provider
from sentinel.vault.manager import get_vault


class ComputerUseQAAgent:
    """Full-spectrum autonomous and co-pilot testing agent."""

    def __init__(
        self,
        target_config: TargetConfig,
        goal: str = "Explore application and verify core flows without errors",
        llm_provider: LLMProvider | None = None,
        event_callback: Callable[[dict[str, Any]], None] | None = None,
        mode: str = "autonomous",
    ) -> None:
        self.target_config = target_config
        self.goal = goal
        self.mode = mode
        self.event_callback = event_callback or (lambda evt: None)
        self.recorder = ActionRecorder(suite_name=f"Studio Agent: {target_config.name}")
        self.adapter = WebAdapter(target_config)
        self.history: list[dict[str, Any]] = []
        self.is_paused = False
        self.is_stopped = False
        self._copilot_event = threading.Event()
        self._copilot_decision: dict[str, Any] = {}

        # Resolve LLM provider (checks vault first, falls back to auto/mock)
        vault = get_vault()
        ant_key = vault.get_key("anthropic")
        if llm_provider:
            self.llm = llm_provider
        elif ant_key and ant_key != "ollama":
            self.llm = get_llm_provider("anthropic", api_key=ant_key)
        else:
            self.llm = get_llm_provider("mock")

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        """Publish real-time telemetry event to Desktop UI via callback."""
        payload = {"type": event_type, "timestamp": time.time(), "data": data}
        try:
            self.event_callback(payload)
        except Exception as exc:
            logger.debug(f"Event callback exception: {exc}")

    def execute_single_action(
        self,
        raw_action: dict[str, Any],
        elements: list[InteractiveElement],
    ) -> GroundedAction:
        """Resolve and execute a single action (manual or autonomous)."""
        grounded = ActionResolver.resolve(raw_action, elements)
        self._emit("action_dispatched", grounded.to_dict())

        # Execute on Playwright target
        try:
            from sentinel.core.schemas import TestStep
            step = TestStep(
                action=grounded.action_type,
                path=grounded.selector or (f"coords({grounded.x},{grounded.y})" if grounded.x else ""),
                body=grounded.value,
            )
            obs = self.adapter.execute_action(step)

            # Record for deterministic CI replay
            self.recorder.record(grounded)

            self._emit("action_completed", {
                "action": grounded.to_dict(),
                "observation": obs.model_dump(mode="json"),
                "status_code": obs.raw_result.get("status_code", 200),
            })
            return grounded
        except Exception as exc:
            logger.error(f"Failed to execute grounded action {grounded}: {exc}")
            self._emit("action_failed", {"action": grounded.to_dict(), "error": str(exc)})
            return grounded

    def run_step(self, step_index: int) -> dict[str, Any]:
        """Perform one complete Observe -> Reason -> Act -> Verify cycle."""
        page = self.adapter._ensure_browser()

        # 1. Observe: Set-of-Marks visual annotation + element extraction
        screenshot_bytes, elements = SetOfMarksAnnotator.annotate_playwright_page(
            page, capture_screenshot=True
        )
        b64_img = base64.b64encode(screenshot_bytes).decode("ascii") if screenshot_bytes else ""

        self._emit("viewport_update", {
            "step": step_index,
            "url": page.url,
            "title": page.title(),
            "screenshot": b64_img,
            "elements_count": len(elements),
            "elements": [e.to_dict() for e in elements[:40]],
        })

        # 2. Reason: Prompt agent with goal, history, and available SoM indexed elements
        compact_elements = [
            f"[{e.index}] {e.tag} {f'id={e.element_id}' if e.element_id else ''} text='{e.text}' role={e.role}"
            for e in elements[:30]
        ]
        elements_summary = "\n".join(compact_elements) if compact_elements else "No interactive elements found."

        prompt = f"""You are Sentinel Studio's Autonomous Senior QA Engineer.
Goal: {self.goal}
Current URL: {page.url}
Page Title: {page.title()}
Step: {step_index}

Interactive Elements visible on screen (identified by badge [index]):
{elements_summary}

Recent Action History:
{json.dumps(self.history[-3:], indent=1) if self.history else "None (Initial Step)"}

Analyze what to test next to accomplish the goal or uncover defects.
Respond in valid JSON with:
{{
  "thought": "Your step-by-step reasoning about the state and planned test",
  "action": "click" | "fill" | "navigate" | "assert" | "wait",
  "target": <badge index number as integer or selector string>,
  "value": <text to type if fill, url if navigate, assertion expression if assert>,
  "assertion": <optional check like 'status_code == 200'>
}}
"""
        self._emit("thought_stream", {
            "status": "thinking",
            "message": f"Analyzing {len(elements)} interactive elements on {page.url}...",
        })

        thought = ""
        action_dict: dict[str, Any] = {}

        try:
            response_text = self.llm.generate(prompt)
            # Extract JSON block
            if "{" in response_text and "}" in response_text:
                json_part = response_text[response_text.find("{") : response_text.rfind("}") + 1]
                action_dict = json.loads(json_part)
                thought = action_dict.get("thought", "Proceeding with next test step.")
            else:
                thought = "Probing primary navigation element."
                action_dict = {"action": "click", "target": 1}
        except Exception:
            # Fallback heuristic if LLM output is non-json
            thought = "Testing first available actionable element."
            action_dict = {"action": "click", "target": 1 if elements else None}

        self._emit("thought_stream", {
            "status": "decided",
            "thought": thought,
            "proposed_action": action_dict,
        })

        # Co-pilot Approval Gate
        if self.mode == "copilot" and not self.is_stopped:
            self._emit("copilot_approval_requested", {
                "step": step_index,
                "thought": thought,
                "proposed_action": action_dict,
                "url": page.url,
            })
            self._copilot_event.clear()
            while not self._copilot_event.is_set() and not self.is_stopped:
                time.sleep(0.2)

            decision = self._copilot_decision.get("decision", "approve")
            if decision == "skip":
                self._emit("copilot_action_skipped", {"step": step_index})
                return {"step": step_index, "skipped": True}
            elif decision == "edit" and self._copilot_decision.get("action"):
                action_dict = self._copilot_decision["action"]

        # 3. Act: Ground and execute
        grounded = self.execute_single_action(action_dict, elements)
        grounded.reasoning = thought

        step_record = {
            "step": step_index,
            "url": page.url,
            "thought": thought,
            "action": grounded.to_dict(),
        }
        self.history.append(step_record)
        return step_record

    def run_autonomous(self, max_steps: int = 10) -> list[dict[str, Any]]:
        """Run continuous autonomous QA loop until goal completion or limit."""
        self._emit("session_started", {
            "goal": self.goal,
            "target": self.target_config.name,
            "max_steps": max_steps,
        })

        # Initial navigation if base_url provided
        if self.target_config.base_url:
            self.execute_single_action(
                {"type": "navigate", "value": self.target_config.base_url},
                [],
            )

        step = 1
        while step <= max_steps and not self.is_stopped:
            while self.is_paused and not self.is_stopped:
                time.sleep(0.5)

            if self.is_stopped:
                break

            try:
                self.run_step(step)
            except Exception as exc:
                logger.error(f"Error during autonomous step {step}: {exc}")
                self._emit("step_error", {"step": step, "error": str(exc)})
            step += 1
            time.sleep(0.8)  # Smooth cadence for visual feedback

        self._emit("session_completed", {
            "total_steps": len(self.history),
            "recorded_suite": self.recorder.to_test_case().model_dump(mode="json"),
        })
        return self.history

    def submit_copilot_decision(self, decision: str, action: dict[str, Any] | None = None) -> None:
        """User approves, edits, or skips the proposed co-pilot action."""
        self._copilot_decision = {"decision": decision, "action": action}
        self._copilot_event.set()

    def capture_viewport(self) -> dict[str, Any]:
        """Capture fresh screenshot and Set-of-Marks annotated elements."""
        page = self.adapter._ensure_browser()
        screenshot_bytes, elements = SetOfMarksAnnotator.annotate_playwright_page(
            page, capture_screenshot=True
        )
        b64_img = base64.b64encode(screenshot_bytes).decode("ascii") if screenshot_bytes else ""
        data = {
            "url": page.url,
            "title": page.title(),
            "screenshot": b64_img,
            "elements_count": len(elements),
            "elements": [e.to_dict() for e in elements[:40]],
        }
        self._emit("viewport_update", data)
        return data

    def pause(self) -> None:
        self.is_paused = True
        self._emit("session_paused", {})

    def resume(self) -> None:
        self.is_paused = False
        self._emit("session_resumed", {})

    def stop(self) -> None:
        self.is_stopped = True
        self._emit("session_stopped", {})

    def close(self) -> None:
        self.stop()
        self.adapter.close()
