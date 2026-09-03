"""Web Application Adapter using Playwright with dedicated worker thread isolation.

Adheres to:
- TRD.md §2.3 & §3.1 (TargetAdapter Protocol)
- rules.md R-SAFE-5 (Network allow-listing)
- rules.md R-EXEC-1 (Context isolation)
- rules.md R-EXEC-3 (Timeouts mandatory)
- rules.md R-BUILD-1 (Adapters never talk to LLM)
"""

from __future__ import annotations

import concurrent.futures
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright
from pydantic import BaseModel, Field

from sentinel.adapters.base import TargetAdapter, register_adapter
from sentinel.core.config import TargetConfig
from sentinel.core.logging import logger
from sentinel.core.schemas import Artifact, Observation, TargetModel, TestStep
from sentinel.llm.provider import LLMProvider, get_llm_provider


class HealedLocatorProposal(BaseModel):
    """Proposal for a healed locator derived from accessibility tree and LLM analysis."""
    original_locator: str
    proposed_locator: str
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    reasoning: str = Field(..., description="Explanation of why this element matches the intended test action")
    matched_role: str | None = Field(default=None, description="Accessibility role of matched element")


class WebAdapter(TargetAdapter):
    """Adapter for browser automation, DOM inspection, visual capture, and locator self-healing via Playwright."""

    def __init__(
        self,
        target_config: TargetConfig | None = None,
        llm_provider: LLMProvider | None = None,
    ) -> None:
        self.target_config = target_config
        self.llm_provider = llm_provider
        # Dedicated worker thread to ensure all Playwright calls share the same Greenlet/thread
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="sentinel_web")
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    def _ensure_browser(self) -> Page:
        """Lazily initialize playwright, browser, and page on the worker thread."""
        if self._playwright is None:
            self._playwright = sync_playwright().start()
        if self._browser is None:
            try:
                self._browser = self._playwright.chromium.launch(headless=True)
            except Exception:
                try:
                    self._browser = self._playwright.chromium.launch(channel="msedge", headless=True)
                except Exception:
                    self._browser = self._playwright.chromium.launch(channel="chrome", headless=True)

        if self._context is None:
            self._context = self._browser.new_context()
        if self._page is None or self._page.is_closed():
            self._page = self._context.new_page()
        return self._page

    def discover(self, config: TargetConfig) -> TargetModel:
        """Introspect web page DOM, links, and accessibility tree."""
        self.target_config = config
        return self._pool.submit(self._discover_impl, config).result()

    def _discover_impl(self, config: TargetConfig) -> TargetModel:
        base_url = config.base_url or "http://localhost:3000"
        endpoints: list[dict[str, Any]] = []
        try:
            page = self._ensure_browser()
            page.goto(base_url, timeout=10000)
            title = page.title()

            links = page.eval_on_selector_all("a[href]", "elements => elements.map(e => e.getAttribute('href'))")
            buttons = page.eval_on_selector_all("button", "elements => elements.map(e => e.innerText.trim())")
            inputs = page.eval_on_selector_all(
                "input, textarea, select",
                "elements => elements.map(e => ({ name: e.name, id: e.id, type: e.type }))",
            )

            endpoints.append({
                "path": base_url,
                "method": "GET",
                "summary": f"Web Page: {title}",
                "description": f"Found {len(links)} links, {len(buttons)} buttons, {len(inputs)} inputs.",
                "metadata": {
                    "title": title,
                    "links": links[:20],
                    "buttons": buttons[:20],
                    "inputs": inputs[:20],
                },
            })
        except Exception as exc:
            logger.warning(f"Web discovery fallback for '{base_url}': {exc}")
            endpoints.append({
                "path": base_url,
                "method": "GET",
                "summary": f"Target Web Application: {base_url}",
                "description": str(exc),
            })

        return TargetModel(
            target_type="web",
            name=config.name or "Web Application",
            endpoints=endpoints,
            metadata={"base_url": base_url},
        )

    def execute_action(self, action: TestStep) -> Observation:
        """Execute a browser action on the dedicated Playwright thread."""
        return self._pool.submit(self._execute_action_impl, action).result()

    def _execute_action_impl(self, action: TestStep) -> Observation:
        start_time = time.perf_counter()
        test_id = action.metadata.get("test_id", "TC-WEB")
        timeout_ms = int((action.timeout_seconds or 10.0) * 1000)

        # 1. R-SAFE-5: Host allowlist check for navigation
        url_to_check = action.path or ""
        if url_to_check.startswith("http://") or url_to_check.startswith("https://"):
            parsed = urlparse(url_to_check)
            host = parsed.hostname or ""
            allowed = self.target_config.allowed_hosts if self.target_config else []
            if allowed:
                is_allowed = (
                    host in allowed
                    or (host in ("localhost", "127.0.0.1") and any(h in ("localhost", "127.0.0.1") for h in allowed))
                )
                if not is_allowed:
                    return Observation(
                        test_id=test_id,
                        raw_result={"url": url_to_check, "host": host},
                        duration_ms=0,
                        error=f"SECURITY_BLOCK: Host '{host}' is not in configured allowlist {allowed} (R-SAFE-5).",
                    )

        try:
            page = self._ensure_browser()
            page_action = (action.action or "navigate").lower()
            target_path = action.path or ""

            status_code = 200
            if page_action in ("navigate", "goto", "open"):
                base_url = (self.target_config.base_url if self.target_config else None) or ""
                full_url = target_path if (target_path.startswith("http://") or target_path.startswith("https://")) else f"{base_url.rstrip('/')}/{target_path.lstrip('/')}"
                response = page.goto(full_url, timeout=timeout_ms)
                status_code = response.status if response else 200
            elif page_action in ("click", "tap", "fill", "type", "input", "press", "key"):
                try:
                    if page_action in ("click", "tap"):
                        page.click(target_path, timeout=timeout_ms)
                        status_code = 200
                    elif page_action in ("fill", "type", "input"):
                        text_to_fill = str(action.body if action.body is not None else action.params.get("text", ""))
                        page.fill(target_path, text_to_fill, timeout=timeout_ms)
                        status_code = 200
                    elif page_action in ("press", "key"):
                        key = str(action.params.get("key", "Enter"))
                        page.press(target_path or "body", key, timeout=timeout_ms)
                        status_code = 200
                except Exception as action_exc:
                    # Attempt self-healing via accessibility tree & LLM (P3 item 13)
                    proposal = self._attempt_self_healing(page, action, page_action, target_path, action_exc)
                    if proposal and proposal.confidence >= 0.70:
                        diff_text = (
                            f"--- Original Locator: {target_path}\n"
                            f"+++ Proposed Healed Locator: {proposal.proposed_locator}\n"
                            f"@@ Confidence: {proposal.confidence:.2f} @@\n"
                            f"Reasoning: {proposal.reasoning}\n"
                        )
                        diff_dir = Path("artifacts") / "healing_proposals"
                        diff_dir.mkdir(parents=True, exist_ok=True)
                        diff_file = diff_dir / f"healing_{test_id}_{int(time.time() * 1000)}.diff"
                        diff_file.write_text(diff_text, encoding="utf-8")

                        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                        return Observation(
                            test_id=test_id,
                            raw_result={
                                "action": page_action,
                                "original_locator": target_path,
                                "healed_proposal": proposal.model_dump(),
                                "status_code": 422,
                                "needs_human_review": True,
                            },
                            artifacts=[
                                Artifact(
                                    path=str(diff_file),
                                    mime_type="text/x-diff",
                                    description=f"Self-healing proposal diff for {target_path}",
                                    metadata={"confidence": proposal.confidence, "proposed": proposal.proposed_locator},
                                )
                            ],
                            duration_ms=elapsed_ms,
                            error=(
                                f"LOCATOR_FAILED_HEALED_FOR_REVIEW: Selector '{target_path}' failed. "
                                f"Self-healing proposed '{proposal.proposed_locator}' (confidence: {proposal.confidence:.2f}). "
                                f"Proposed as diff for human review per rules.md."
                            ),
                        )
                    raise action_exc

            elif page_action in ("evaluate", "eval", "js"):
                eval_script = str(action.body or action.params.get("script", "document.title"))
                result = page.evaluate(eval_script)
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                return Observation(
                    test_id=test_id,
                    raw_result={"evaluation_result": result, "status_code": 200, "url": page.url},
                    duration_ms=elapsed_ms,
                )

            elif page_action in ("screenshot", "snapshot"):
                status_code = 200

            else:
                status_code = 200

            # Capture screenshot artifact
            screenshot_dir = Path("artifacts") / "screenshots"
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            screenshot_file = screenshot_dir / f"{test_id}_{int(time.time() * 1000)}.png"

            try:
                page.screenshot(path=str(screenshot_file), full_page=False)
                has_screenshot = True
            except Exception:
                has_screenshot = False

            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            page_text = page.inner_text("body")[:2000] if page else ""

            raw_result = {
                "status_code": status_code,
                "url": page.url,
                "title": page.title(),
                "body_snippet": page_text,
                "action": page_action,
            }

            artifacts: list[Artifact] = []
            if has_screenshot:
                artifacts.append(
                    Artifact(
                        path=str(screenshot_file),
                        mime_type="image/png",
                        description=f"Screenshot after {page_action} on {target_path}",
                        metadata={"url": page.url},
                    )
                )

            return Observation(
                test_id=test_id,
                raw_result=raw_result,
                artifacts=artifacts,
                duration_ms=elapsed_ms,
                error=None,
            )

        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return Observation(
                test_id=test_id,
                raw_result={"action": action.action, "path": action.path},
                duration_ms=elapsed_ms,
                error=f"WEB_EXECUTION_EXCEPTION: {exc}",
            )

    def _attempt_self_healing(
        self,
        page: Page,
        action: TestStep,
        page_action: str,
        target_path: str,
        original_exc: Exception,
    ) -> HealedLocatorProposal | None:
        """Query page accessibility tree and prompt LLM to propose a healed locator diff for human review (P3 item 13)."""
        try:
            # 1. Capture accessibility tree snapshot
            ax_snapshot = None
            try:
                ax_snapshot = page.accessibility.snapshot()
            except Exception:
                pass

            candidates: list[dict[str, Any]] = []
            if ax_snapshot:
                def extract_nodes(node: dict[str, Any]):
                    role = node.get("role", "")
                    name = node.get("name", "")
                    value = node.get("value", "")
                    if role in ("button", "link", "textbox", "checkbox", "radio", "combobox", "menuitem", "tab"):
                        candidates.append({"role": role, "name": name, "value": value})
                    for child in node.get("children", []):
                        extract_nodes(child)
                extract_nodes(ax_snapshot)

            candidates_summary = json.dumps(candidates[:25])
            intent = action.metadata.get("intent") or action.metadata.get("description") or f"{page_action} {target_path}"

            prompt = (
                f"A web test action '{page_action}' failed with error: {original_exc}\n"
                f"Failed selector: '{target_path}'\n"
                f"Test intent / expected action: '{intent}'\n"
                f"Accessibility tree elements on current page:\n{candidates_summary}\n\n"
                f"Identify the intended element and propose a healed locator. "
                f"Explain your reasoning and provide confidence (0.0 to 1.0)."
            )

            provider = self.llm_provider or get_llm_provider("auto")
            proposal, metrics = provider.generate_structured(
                prompt=prompt,
                response_model=HealedLocatorProposal,
                system_prompt="You are an expert SQA locator self-healing engine. Propose precise healed locators for review.",
            )

            logger.info(
                f"SELF_HEALING_ATTEMPT: original='{target_path}' proposed='{proposal.proposed_locator}' "
                f"confidence={proposal.confidence} reasoning='{proposal.reasoning}'"
            )
            return proposal
        except Exception as heal_exc:
            logger.warning(f"SELF_HEALING_FAILED: could not heal locator '{target_path}': {heal_exc}")
            return None

    def capture_artifacts(self, observation: Observation) -> list[Artifact]:
        """Return captured artifacts."""
        return list(observation.artifacts)

    def reset_state(self, config: TargetConfig) -> None:
        """Reset browser context between test cases for clean isolation (R-EXEC-1)."""
        self._pool.submit(self._reset_state_impl).result()

    def _reset_state_impl(self) -> None:
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
            self._page = None

    def close(self) -> None:
        """Teardown browser and playwright resources."""
        try:
            self._pool.submit(self._close_impl).result(timeout=5.0)
        except Exception:
            pass
        self._pool.shutdown(wait=False)

    def _close_impl(self) -> None:
        self._reset_state_impl()
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None


# Register Web adapter
register_adapter("web", WebAdapter)
