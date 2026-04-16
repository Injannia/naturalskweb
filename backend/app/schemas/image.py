from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_IMAGE_EXTS: set[str] = {"jpg", "jpeg", "png", "webp", "bmp", "tiff"}
MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20 MB
INPAINT_METHODS: set[str] = {"telea", "ns"}


# ---------------------------------------------------------------------------
# Mask shape model
# ---------------------------------------------------------------------------


class MaskShape(BaseModel):
    """A single mask shape drawn by the user on the image canvas.

    Coordinates in ``points`` are normalized to [0, 1] relative to the
    original image dimensions.
    """

    type: str = Field(..., description="Shape type: 'brush' or 'rect'")
    points: list[list[float]] = Field(..., description="List of [x, y] coordinate pairs (normalised 0-1)")
    brush_size: float | None = Field(None, description="Brush stroke width (normalised 0-1)")
    is_eraser: bool = Field(False, description="When True this shape subtracts from the mask instead of adding")

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in ("brush", "rect"):
            raise ValueError("type must be 'brush' or 'rect'")
        return v


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class RemoveBgRequest(BaseModel):
    task_id: str


class RemoveWatermarkRequest(BaseModel):
    task_id: str
    mask: list[MaskShape]
    inpaint_method: str = "telea"

    @field_validator("inpaint_method")
    @classmethod
    def validate_inpaint_method(cls, v: str) -> str:
        if v not in INPAINT_METHODS:
            raise ValueError(f"inpaint_method must be one of {INPAINT_METHODS}")
        return v


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class ImageUploadResponse(BaseModel):
    task_id: str
    original_filename: str
    original_ext: str
    file_size: int


class ImageTaskStatus(BaseModel):
    model_config = ConfigDict(extra="ignore")

    task_id: str
    status: str
    progress: float
    operation: str
    filename: str | None = None
    file_size: int | None = None
    error: str | None = None
    original_filename: str
    original_ext: str
    inpaint_method: str | None = None
    created_at: str | None = None
    completed_at: str | None = None


class ImageTaskListItem(BaseModel):
    task_id: str
    status: str
    progress: float
    operation: str
    filename: str | None = None
    file_size: int | None = None
    error: str | None = None
    original_filename: str
    original_ext: str
    inpaint_method: str | None = None
    created_at: str | None = None
    completed_at: str | None = None
    file_exists: bool = False


class ImageQuotaResponse(BaseModel):
    """Daily image processing quota status for the current user."""

    used: int
    limit: int
