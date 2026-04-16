from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Allowed input extensions mapped to their category
# ---------------------------------------------------------------------------
ALLOWED_INPUT_EXTS: dict[str, str] = {
    # video
    "mp4": "video", "avi": "video", "mkv": "video", "mov": "video",
    "wmv": "video", "flv": "video", "webm": "video",
    # audio
    "mp3": "audio", "wav": "audio", "ogg": "audio", "flac": "audio",
    "aac": "audio", "wma": "audio", "m4a": "audio",
    # image
    "jpg": "image", "jpeg": "image", "png": "image", "bmp": "image",
    "tiff": "image", "webp": "image", "gif": "image", "ico": "image",
    # document
    "docx": "document", "doc": "document", "odt": "document", "rtf": "document",
    "txt": "document", "xlsx": "document", "xls": "document", "csv": "document",
    "pptx": "document", "ppt": "document",
}

VIDEO_OUTPUT_FORMATS = ["mp4", "avi", "mkv", "mov", "webm"]
AUDIO_OUTPUT_FORMATS = ["mp3", "wav", "ogg", "flac", "aac"]
IMAGE_OUTPUT_FORMATS = ["jpg", "png", "bmp", "tiff", "webp", "gif", "ico"]
DOCUMENT_OUTPUT_FORMATS = ["pdf", "docx", "odt", "txt", "html", "xlsx", "csv"]

BLOCKED_EXTENSIONS = {"exe", "bat", "cmd", "sh", "ps1", "com", "scr", "msi", "dll", "so", "bin"}

MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB
MAX_BATCH_SIZE = 20


# ---------------------------------------------------------------------------
# Conversion option models — one per category
# ---------------------------------------------------------------------------


class VideoConvertOptions(BaseModel):
    resolution: str | None = None      # e.g. "1920x1080", "1280x720"
    codec: str | None = None           # e.g. "h264", "h265", "vp9"
    bitrate: str | None = None         # e.g. "2M", "5M"
    fps: int | None = Field(None, ge=1, le=120)
    audio_codec: str | None = None     # e.g. "aac", "mp3", "copy"


class AudioConvertOptions(BaseModel):
    bitrate: str | None = None         # e.g. "128k", "320k"
    sample_rate: int | None = Field(None, ge=8000, le=192000)
    channels: int | None = Field(None, ge=1, le=2)


class ImageConvertOptions(BaseModel):
    quality: int | None = Field(None, ge=1, le=100)
    width: int | None = Field(None, ge=1, le=10000)
    height: int | None = Field(None, ge=1, le=10000)
    keep_aspect: bool = True


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class ConvertStartRequest(BaseModel):
    task_id: str
    target_format: str
    options: dict | None = None


class BatchConvertRequest(BaseModel):
    items: list[ConvertStartRequest] = Field(..., max_length=20)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class UploadResponse(BaseModel):
    task_id: str
    original_filename: str
    original_ext: str
    category: str
    file_size: int


class CapabilitiesResponse(BaseModel):
    category: str
    target_formats: list[str]
    settings_fields: dict


class ConvertTaskStatus(BaseModel):
    task_id: str
    status: str
    progress: float
    filename: str | None = None
    file_size: int | None = None
    error: str | None = None
    original_filename: str
    original_ext: str
    category: str
    target_format: str | None = None
    options: dict | None = None
    created_at: str | None = None
    completed_at: str | None = None
    batch_id: str | None = None


class ConvertTaskListItem(BaseModel):
    task_id: str
    status: str
    progress: float
    filename: str | None = None
    file_size: int | None = None
    error: str | None = None
    original_filename: str
    original_ext: str
    category: str
    target_format: str | None = None
    created_at: str | None = None
    completed_at: str | None = None
    batch_id: str | None = None
    file_exists: bool = False


class QuotaResponse(BaseModel):
    """Daily conversion quota status for the current user."""

    used: int
    limit: int
