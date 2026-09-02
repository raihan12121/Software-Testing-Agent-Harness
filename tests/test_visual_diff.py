"""Unit tests for VisualDiffChecker."""

from pathlib import Path

from PIL import Image

from sentinel.oracle.visual_diff import VisualDiffChecker


def test_visual_diff_identical_images(tmp_path: Path):
    img1_path = tmp_path / "img1.png"
    img2_path = tmp_path / "img2.png"

    # Create two identical 50x50 red images
    img1 = Image.new("RGB", (50, 50), color="red")
    img1.save(img1_path)
    img1.save(img2_path)

    matches, diff_pct, diff_file = VisualDiffChecker.compare_images(img1_path, img2_path)
    assert matches is True
    assert diff_pct == 0.0
    assert diff_file is None


def test_visual_diff_differing_images(tmp_path: Path):
    img1_path = tmp_path / "img1.png"
    img2_path = tmp_path / "img2.png"
    diff_out = tmp_path / "diff.png"

    img1 = Image.new("RGB", (50, 50), color="white")
    img2 = Image.new("RGB", (50, 50), color="black")
    img1.save(img1_path)
    img2.save(img2_path)

    matches, diff_pct, diff_file = VisualDiffChecker.compare_images(
        img1_path, img2_path, diff_output_path=diff_out, tolerance_pct=0.01
    )
    assert matches is False
    assert diff_pct > 0.5
    assert diff_file is not None
    assert diff_file.exists()
