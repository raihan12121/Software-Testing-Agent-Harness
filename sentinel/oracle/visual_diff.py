"""Visual regression checking and screenshot diffing.

Adheres to:
- phases.md §Phase 2 (Visual regression checking as deterministic pre-check)
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Tuple

from PIL import Image, ImageChops, ImageStat


class VisualDiffChecker:
    """Performs deterministic pixel-by-pixel screenshot comparisons."""

    @staticmethod
    def compare_images(
        baseline_path: str | Path,
        actual_path: str | Path,
        diff_output_path: str | Path | None = None,
        tolerance_pct: float = 0.01,
    ) -> Tuple[bool, float, Path | None]:
        """Compare two images and return (matches, diff_percentage, diff_image_path)."""
        base_p = Path(baseline_path)
        actual_p = Path(actual_path)

        if not base_p.exists() or not actual_p.exists():
            raise FileNotFoundError(f"One or both images do not exist: {base_p}, {actual_p}")

        img1 = Image.open(base_p).convert("RGB")
        img2 = Image.open(actual_p).convert("RGB")

        # Resize if dimensions differ slightly to enable comparison
        if img1.size != img2.size:
            img2 = img2.resize(img1.size)

        # Compute difference
        diff = ImageChops.difference(img1, img2)
        stat = ImageStat.Stat(diff)

        # Root mean square (RMS) error per band
        rms = math.sqrt(sum(s**2 for s in stat.rms) / len(stat.rms))
        max_possible_rms = 255.0
        diff_pct = rms / max_possible_rms

        matches = diff_pct <= tolerance_pct
        diff_file = None

        if not matches and diff_output_path:
            diff_file = Path(diff_output_path)
            diff_file.parent.mkdir(parents=True, exist_ok=True)
            diff.save(diff_file)

        return matches, round(diff_pct, 4), diff_file
