import pytest
from pydantic import ValidationError

from app.schemas.multidl import DownloadRequest, InfoRequest, DownloadStatus


def test_schema_download_request_valid():
    req = DownloadRequest(url="https://www.tiktok.com/@user/video/123", audio_only=True)
    assert req.audio_only is True
    assert req.url.startswith("https://")


def test_schema_download_request_defaults_video():
    req = DownloadRequest(url="https://vk.com/video-1_1")
    assert req.audio_only is False


def test_schema_download_request_rejects_blank():
    with pytest.raises(ValidationError):
        DownloadRequest(url="   ")


def test_schema_status_literal_accepts_converting():
    s = DownloadStatus(task_id="t1", status="converting", progress=10.0)
    assert s.status == "converting"
