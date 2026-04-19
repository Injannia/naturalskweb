"""Regression tests for preview file lookup in the image router.

The helpers ``_find_preview`` and ``_find_result_preview`` used to sort by
filename, which is UUID-random — leading to the result-preview endpoint
returning the *input* preview about 50% of the time. They must sort by
mtime instead: oldest = input, newest = result.
"""
import os
import time

from app.routers.image import _find_preview, _find_result_preview


def _touch(path: str, mtime: float) -> None:
    """Create an empty file with a deterministic mtime."""
    with open(path, "wb") as f:
        f.write(b"\x00")
    os.utime(path, (mtime, mtime))


def test_find_result_preview_returns_newest_when_uuid_order_inverted(tmp_path):
    """Result preview must be picked by mtime, not alphabetical UUID order.

    We use names where the alphabetically-LAST file is the INPUT preview
    (the old, buggy behavior would return this one).
    """
    task_dir = str(tmp_path)

    # Input preview created first — UUID lexicographically GREATER.
    input_preview = os.path.join(task_dir, "preview_zzzzzz.jpg")
    # Result file
    result_filename = "result.png"
    result_path = os.path.join(task_dir, result_filename)
    # Result preview created later — UUID lexicographically SMALLER.
    result_preview = os.path.join(task_dir, "preview_000000.jpg")

    now = time.time()
    _touch(input_preview, now - 20)
    _touch(result_path, now - 10)
    _touch(result_preview, now - 5)

    found = _find_result_preview(task_dir, result_filename)
    assert found == result_preview, (
        "Expected newest preview (result), got alphabetically-last input"
    )


def test_find_preview_returns_oldest_when_uuid_order_inverted(tmp_path):
    """Input preview must be picked by mtime (oldest), not alphabetical order."""
    task_dir = str(tmp_path)

    input_preview = os.path.join(task_dir, "preview_zzzzzz.jpg")
    result_preview = os.path.join(task_dir, "preview_000000.jpg")

    now = time.time()
    _touch(input_preview, now - 20)
    _touch(result_preview, now - 5)

    found = _find_preview(task_dir)
    assert found == input_preview, (
        "Expected oldest preview (input), got alphabetically-first result"
    )


def test_find_result_preview_single_preview_falls_back_to_mtime(tmp_path):
    """When only one preview exists but it post-dates the result, return it."""
    task_dir = str(tmp_path)
    result_filename = "result.png"
    result_path = os.path.join(task_dir, result_filename)
    lone_preview = os.path.join(task_dir, "preview_abcdef.jpg")

    now = time.time()
    _touch(result_path, now - 10)
    _touch(lone_preview, now - 5)

    assert _find_result_preview(task_dir, result_filename) == lone_preview


def test_find_result_preview_missing_dir_returns_none(tmp_path):
    missing = str(tmp_path / "does-not-exist")
    assert _find_result_preview(missing, "any.png") is None


def test_find_preview_missing_dir_returns_none(tmp_path):
    missing = str(tmp_path / "does-not-exist")
    assert _find_preview(missing) is None
