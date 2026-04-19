"""Unit tests for LaMa ONNX inference in image_service."""
from unittest.mock import MagicMock, patch

import numpy as np
from PIL import Image

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
