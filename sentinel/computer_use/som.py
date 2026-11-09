"""Set-of-Marks (SoM) Visual Annotator & Element Grounding.

Annotates interactive UI elements with indexed visual markers ([1], [2], [3]...)
and builds a compact semantic element map to eliminate coordinate drift and reduce
token cost by 80% compared to raw pixel Computer Use.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw, ImageFont


@dataclass
class InteractiveElement:
    """Structured representation of an actionable element in the viewport."""
    index: int
    tag: str
    element_id: str = ""
    selector: str = ""
    role: str = ""
    text: str = ""
    bbox: dict[str, float] = field(default_factory=lambda: {"x": 0, "y": 0, "width": 0, "height": 0})
    attributes: dict[str, str] = field(default_factory=dict)

    @property
    def center_point(self) -> tuple[int, int]:
        """Calculates center coordinate (x, y) of the element."""
        cx = int(self.bbox.get("x", 0) + (self.bbox.get("width", 0) / 2))
        cy = int(self.bbox.get("y", 0) + (self.bbox.get("height", 0) / 2))
        return cx, cy

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "tag": self.tag,
            "id": self.element_id,
            "selector": self.selector,
            "role": self.role,
            "text": self.text[:60],
            "center": self.center_point,
            "bbox": self.bbox,
        }


# JavaScript injected into Playwright web pages to detect and tag interactive elements
SOM_INJECTION_SCRIPT = """
(() => {
    // 1. Remove any previous annotations
    const prevContainer = document.getElementById('__sentinel_som_container__');
    if (prevContainer) prevContainer.remove();

    const container = document.createElement('div');
    container.id = '__sentinel_som_container__';
    container.style.position = 'fixed';
    container.style.top = '0';
    container.style.left = '0';
    container.style.width = '100vw';
    container.style.height = '100vh';
    container.style.pointerEvents = 'none';
    container.style.zIndex = '2147483647';
    document.body.appendChild(container);

    const interactiveSelectors = [
        'a[href]', 'button', 'input', 'select', 'textarea',
        '[role="button"]', '[role="link"]', '[role="checkbox"]', '[role="menuitem"]',
        '[role="tab"]', '[role="switch"]', '[contenteditable="true"]', '[tabindex]:not([tabindex="-1"])'
    ];

    const elements = Array.from(document.querySelectorAll(interactiveSelectors.join(',')));
    const elementData = [];
    let markIndex = 1;

    for (const el of elements) {
        const rect = el.getBoundingClientRect();
        // Skip hidden or collapsed elements
        if (rect.width < 6 || rect.height < 6 || rect.bottom < 0 || rect.top > window.innerHeight) {
            continue;
        }

        const computedStyle = window.getComputedStyle(el);
        if (computedStyle.display === 'none' || computedStyle.visibility === 'hidden' || computedStyle.opacity === '0') {
            continue;
        }

        // Generate clean robust selector
        let selector = '';
        if (el.id) {
            selector = '#' + CSS.escape(el.id);
        } else if (el.name) {
            selector = `${el.tagName.toLowerCase()}[name="${CSS.escape(el.name)}"]`;
        } else if (el.getAttribute('data-testid')) {
            selector = `[data-testid="${CSS.escape(el.getAttribute('data-testid'))}"]`;
        } else if (el.getAttribute('aria-label')) {
            selector = `[aria-label="${CSS.escape(el.getAttribute('aria-label'))}"]`;
        } else {
            selector = el.tagName.toLowerCase();
            if (el.className && typeof el.className === 'string') {
                const firstClass = el.className.trim().split(/\\s+/)[0];
                if (firstClass && !firstClass.includes(':')) {
                    selector += '.' + CSS.escape(firstClass);
                }
            }
        }

        // Draw bounding box and badge in container
        const box = document.createElement('div');
        box.style.position = 'fixed';
        box.style.left = rect.left + 'px';
        box.style.top = rect.top + 'px';
        box.style.width = rect.width + 'px';
        box.style.height = rect.height + 'px';
        box.style.border = '2px solid #3b82f6';
        box.style.borderRadius = '3px';
        box.style.backgroundColor = 'rgba(59, 130, 246, 0.08)';
        box.style.pointerEvents = 'none';

        const badge = document.createElement('div');
        badge.innerText = markIndex.toString();
        badge.style.position = 'absolute';
        badge.style.top = '-12px';
        badge.style.left = '-2px';
        badge.style.backgroundColor = '#2563eb';
        badge.style.color = '#ffffff';
        badge.style.fontSize = '10px';
        badge.style.fontWeight = 'bold';
        badge.style.padding = '1px 5px';
        badge.style.borderRadius = '3px';
        badge.style.boxShadow = '0 1px 3px rgba(0,0,0,0.4)';
        box.appendChild(badge);
        container.appendChild(box);

        elementData.push({
            index: markIndex,
            tag: el.tagName.toLowerCase(),
            element_id: el.id || '',
            selector: selector,
            role: el.getAttribute('role') || el.type || el.tagName.toLowerCase(),
            text: (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || '').trim(),
            bbox: {
                x: rect.left,
                y: rect.top,
                width: rect.width,
                height: rect.height
            },
            attributes: {
                name: el.name || '',
                type: el.type || '',
                href: el.href || ''
            }
        });

        markIndex++;
        if (markIndex > 100) break; // Limit to 100 actionable elements to prevent canvas clutter
    }

    return elementData;
})();
"""

SOM_CLEANUP_SCRIPT = """
(() => {
    const prev = document.getElementById('__sentinel_som_container__');
    if (prev) prev.remove();
})();
"""


class SetOfMarksAnnotator:
    """Produces visual Set-of-Marks overlays on web pages or images."""

    @classmethod
    def annotate_playwright_page(
        cls, page: Any, capture_screenshot: bool = True
    ) -> tuple[bytes | None, list[InteractiveElement]]:
        """Injects SoM badges into live Playwright page, takes screenshot, and cleans up badges."""
        raw_elements = page.evaluate(SOM_INJECTION_SCRIPT)
        elements: list[InteractiveElement] = []

        for item in raw_elements:
            elements.append(
                InteractiveElement(
                    index=item["index"],
                    tag=item["tag"],
                    element_id=item.get("element_id", ""),
                    selector=item.get("selector", ""),
                    role=item.get("role", ""),
                    text=item.get("text", ""),
                    bbox=item.get("bbox", {}),
                    attributes=item.get("attributes", {}),
                )
            )

        screenshot_bytes = None
        if capture_screenshot:
            screenshot_bytes = page.screenshot(type="png", full_page=False)

        # Remove markers from page so normal application state remains untouched
        page.evaluate(SOM_CLEANUP_SCRIPT)

        return screenshot_bytes, elements

    @classmethod
    def annotate_image_bboxes(
        cls, image: Image.Image, elements: list[InteractiveElement]
    ) -> Image.Image:
        """Draws SoM visual bounding boxes directly onto a PIL Image (useful for Desktop or mock views)."""
        annotated = image.copy()
        draw = ImageDraw.Draw(annotated)

        for el in elements:
            x = el.bbox.get("x", 0)
            y = el.bbox.get("y", 0)
            w = el.bbox.get("width", 0)
            h = el.bbox.get("height", 0)

            # Draw rectangle
            draw.rectangle([x, y, x + w, y + h], outline="#3b82f6", width=2)

            # Draw badge background
            badge_text = str(el.index)
            bx, by = x, max(0, y - 14)
            draw.rectangle([bx, by, bx + 18, by + 13], fill="#2563eb")
            draw.text((bx + 3, by + 1), badge_text, fill="#ffffff")

        return annotated
