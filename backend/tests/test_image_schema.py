"""Schema validation tests for RemoveWatermarkRequest."""
import pytest
from pydantic import ValidationError

from app.schemas.image import RemoveWatermarkRequest, MaskShape


def _minimal_shape() -> MaskShape:
    return MaskShape(type="rect", points=[[0.1, 0.1], [0.2, 0.2]])


def test_inpaint_method_lama_is_accepted():
    req = RemoveWatermarkRequest(
        task_id="abc",
        mask=[_minimal_shape()],
        inpaint_method="lama",
    )
    assert req.inpaint_method == "lama"


def test_inpaint_method_telea_is_accepted():
    req = RemoveWatermarkRequest(
        task_id="abc",
        mask=[_minimal_shape()],
        inpaint_method="telea",
    )
    assert req.inpaint_method == "telea"


def test_inpaint_method_ns_is_accepted():
    req = RemoveWatermarkRequest(
        task_id="abc",
        mask=[_minimal_shape()],
        inpaint_method="ns",
    )
    assert req.inpaint_method == "ns"


def test_inpaint_method_unknown_raises():
    with pytest.raises(ValidationError):
        RemoveWatermarkRequest(
            task_id="abc",
            mask=[_minimal_shape()],
            inpaint_method="sdxl",
        )
