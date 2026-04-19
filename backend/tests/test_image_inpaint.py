"""Unit tests for LaMa ONNX inference in image_service."""
import os
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from app.core.config import settings
from app.services import image_service


def test_lama_session_lazy_init(tmp_path, monkeypatch):
    """_get_lama_session returns same session across calls; InferenceSession is called once."""
    image_service._lama_session = None  # reset cache

    fake_file = tmp_path / "lama.onnx"
    fake_file.write_bytes(b"fake onnx bytes")
    monkeypatch.setattr(image_service, "_LAMA_CACHE_FILE", fake_file)

    fake_session = MagicMock(name="InferenceSession")
    fake_ort = MagicMock()
    fake_ort.InferenceSession = MagicMock(return_value=fake_session)

    with patch.dict("sys.modules", {"onnxruntime": fake_ort}):
        first = image_service._get_lama_session()
        second = image_service._get_lama_session()

    assert first is fake_session
    assert second is fake_session
    assert fake_ort.InferenceSession.call_count == 1

    image_service._lama_session = None  # cleanup


def test_run_lama_onnx_preserves_shape(monkeypatch):
    """_run_lama_onnx returns a PIL image of the same size as input."""
    img = Image.new("RGB", (64, 48), color=(120, 200, 100))
    mask = Image.new("L", (64, 48), color=0)

    # Model output 'image' is (1, 3, H, W) where H=48, W=64 (already multiples of 8)
    fake_output = np.full((1, 3, 48, 64), 255, dtype=np.float32)
    fake_session = MagicMock()
    fake_session.run.return_value = [fake_output]
    monkeypatch.setattr(image_service, "_get_lama_session", lambda: fake_session)

    result = image_service._run_lama_onnx(img, mask)

    assert isinstance(result, Image.Image)
    assert result.size == (64, 48)
    assert fake_session.run.call_count == 1


@pytest.fixture
def task_dir_with_input(tmp_path, monkeypatch):
    """Create a task directory with a 1024x768 JPG input file."""
    task_id = "test-task-123"
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    task_dir = tmp_path / task_id
    task_dir.mkdir()
    arr = np.full((768, 1024, 3), 200, dtype=np.uint8)
    Image.fromarray(arr).save(task_dir / "input_abc.jpg")
    return task_id


@pytest.fixture
def large_task_dir(tmp_path, monkeypatch):
    """Create a task directory with a 3000x2000 input file (triggers LaMa downsample)."""
    task_id = "test-large-456"
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    task_dir = tmp_path / task_id
    task_dir.mkdir()
    arr = np.full((2000, 3000, 3), 200, dtype=np.uint8)
    Image.fromarray(arr).save(task_dir / "input_xyz.jpg")
    return task_id


def _rect_shape():
    return {"type": "rect", "points": [[0.3, 0.3], [0.6, 0.6]], "brush_size": None, "is_eraser": False}


def test_telea_uses_radius_10_and_dilates_mask(task_dir_with_input):
    """TELEA branch calls cv2.inpaint with inpaintRadius=10 after dilating the mask."""
    with patch.object(image_service.cv2, "inpaint", wraps=image_service.cv2.inpaint) as inpaint_spy, \
         patch.object(image_service.cv2, "dilate", wraps=image_service.cv2.dilate) as dilate_spy:
        result = image_service._remove_watermark_sync(
            task_dir_with_input,
            [_rect_shape()],
            "telea",
        )

    assert dilate_spy.call_count == 1
    assert inpaint_spy.call_count == 1
    _, _, radius_arg, flags_arg = inpaint_spy.call_args.args
    assert radius_arg == 10
    assert flags_arg == image_service.cv2.INPAINT_TELEA
    assert result["filename"].endswith(".png")


def test_ns_uses_radius_10(task_dir_with_input):
    with patch.object(image_service.cv2, "inpaint", wraps=image_service.cv2.inpaint) as inpaint_spy:
        image_service._remove_watermark_sync(
            task_dir_with_input,
            [_rect_shape()],
            "ns",
        )
    _, _, radius_arg, flags_arg = inpaint_spy.call_args.args
    assert radius_arg == 10
    assert flags_arg == image_service.cv2.INPAINT_NS


def test_lama_branch_calls_run_lama_with_pil_images(task_dir_with_input, monkeypatch):
    """LaMa branch invokes _run_lama_onnx with PIL Image + PIL mask."""
    fake_result = Image.new("RGB", (1024, 768), color=(128, 128, 128))
    fake_run = MagicMock(return_value=fake_result)
    monkeypatch.setattr(image_service, "_run_lama_onnx", fake_run)

    result = image_service._remove_watermark_sync(
        task_dir_with_input,
        [_rect_shape()],
        "lama",
    )

    assert fake_run.call_count == 1
    call_img, call_mask = fake_run.call_args.args
    assert isinstance(call_img, Image.Image)
    assert isinstance(call_mask, Image.Image)
    assert call_img.size == (1024, 768)
    assert call_mask.size == (1024, 768)
    assert result["filename"].endswith(".png")


def test_lama_branch_downsamples_large_inputs(large_task_dir, monkeypatch):
    """LaMa input > 1536 px on the longest side is downsampled before inference."""
    fake_result = Image.new("RGB", (1536, 1024), color=(128, 128, 128))
    fake_run = MagicMock(return_value=fake_result)
    monkeypatch.setattr(image_service, "_run_lama_onnx", fake_run)

    result = image_service._remove_watermark_sync(
        large_task_dir,
        [_rect_shape()],
        "lama",
    )

    call_img, _ = fake_run.call_args.args
    assert max(call_img.size) == 1536  # downsampled from 3000
    assert result["filename"].endswith(".png")

    task_dir = os.path.join(settings.UPLOAD_DIR, large_task_dir)
    final = Image.open(os.path.join(task_dir, result["filename"]))
    assert final.size == (3000, 2000)
