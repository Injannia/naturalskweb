# Image Processor Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Существенно повысить качество удаления фона и водяных знаков на CPU-железе, исправить неудобный UX сравнения «До/После».

**Architecture:** Модель rembg переводится с `u2netp` на `birefnet-general-lite` с alpha matting. Для inpainting-а добавляется LaMa через прямой `onnxruntime` как дефолтный метод, классические TELEA/NS остаются. Веса `lama.onnx` (~200 МБ) скачиваются один раз при первом обращении в `~/.cache/naturalskweb/lama/`. Маска автоматически дилатируется перед инференсом. На фронте `ImageCompare` переделывается: три режима отображения (До / Сравнить / После), инверсия семантики (слева — «До», справа — «После»), клавиатурная навигация, шашечка прозрачности для PNG.

**Tech Stack:** FastAPI · SQLAlchemy · rembg (BiRefNet) · onnxruntime (LaMa) · OpenCV · Pillow · React 18 · TypeScript · Vite · pytest

**Spec:** `docs/superpowers/specs/2026-04-19-image-processor-quality-design.md`

---

## File Structure

**Backend — изменяются:**
- `backend/requirements.txt` — добавить `onnxruntime`, поднять `rembg`
- `backend/app/schemas/image.py` — расширить `INPAINT_METHODS` на `"lama"`
- `backend/app/services/image_service.py` — новая константа модели rembg, ленивый загрузчик LaMa, переработка `_remove_bg_sync` и `_remove_watermark_sync`
- `backend/app/main.py` — прогрев моделей в lifespan

**Backend — создаются:**
- `backend/tests/test_image_inpaint.py` — unit-тесты веток lama/telea/ns, дилатации, даунсемплинга
- `backend/tests/test_image_schema.py` — валидация `inpaint_method`

**Frontend — изменяются:**
- `frontend/src/pages/ImageProcessor/types.ts` — `InpaintMethod` добавить `'lama'`
- `frontend/src/pages/ImageProcessor/components/WatermarkRemoval.tsx` — дефолт lama, новые опции, подсказка
- `frontend/src/pages/ImageProcessor/components/WatermarkRemoval.module.css` — стиль подсказки
- `frontend/src/pages/ImageProcessor/components/BackgroundRemoval.tsx` — передача `transparencyGrid`
- `frontend/src/pages/ImageProcessor/components/ImageCompare.tsx` — полная переработка
- `frontend/src/pages/ImageProcessor/components/ImageCompare.module.css` — стили режимов, шашечки, клавиатурного фокуса

---

### Task 0: Добавить зависимости и проверить размер установки ✅ DONE (commit 797cde9)

**Goal:** Установить `onnxruntime` и актуальную `rembg`, убедиться, что сборка не ломается.

**Files:**
- Modify: `backend/requirements.txt`

**Acceptance Criteria:**
- [x] `onnxruntime>=1.16.0` добавлен
- [x] `rembg[cpu]>=2.0.56` (было `>=2.0.50`) для поддержки `birefnet-general-lite`
- [x] `pip install -r requirements.txt` проходит без ошибок
- [x] `python -c "import onnxruntime; from rembg import new_session"` выполняется

**Note:** Первоначально был выбран пакет `simple-lama-inpainting`, но его метаданные пинят `pillow<10.0.0`, что конфликтует с проектом. Пакет `iopaint` как альтернатива пинит `Pillow==9.5.0` (ещё жёстче) плюс тянет diffusers/transformers/gradio. Поэтому решено использовать прямой `onnxruntime` с ручной загрузкой весов `lama.onnx` (см. Task 2).

---

### Task 1: Расширить схему `InpaintMethod` значением `lama`

**Goal:** Принимать `"lama"` как валидное значение `inpaint_method` в API.

**Files:**
- Modify: `backend/app/schemas/image.py`
- Create: `backend/tests/test_image_schema.py`

**Acceptance Criteria:**
- [ ] `INPAINT_METHODS` содержит `"lama"`, `"telea"`, `"ns"`
- [ ] Pydantic-запрос с `{"inpaint_method": "lama"}` валиден
- [ ] Pydantic-запрос с `{"inpaint_method": "unknown"}` вызывает ValidationError

**Verify:** `cd backend && pytest tests/test_image_schema.py -v` → 3 passed

**Steps:**

- [ ] **Step 1: Написать падающие тесты**

Создать `backend/tests/test_image_schema.py`:

```python
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
```

- [ ] **Step 2: Запустить тесты — `lama` должен падать**

```bash
cd backend && pytest tests/test_image_schema.py -v
```

Expected: `test_inpaint_method_lama_is_accepted` FAIL (ValidationError), остальные PASS.

- [ ] **Step 3: Расширить `INPAINT_METHODS`**

В `backend/app/schemas/image.py` изменить строку:

```python
INPAINT_METHODS: set[str] = {"telea", "ns"}
```

на:

```python
INPAINT_METHODS: set[str] = {"lama", "telea", "ns"}
```

- [ ] **Step 4: Запустить тесты — все должны пройти**

```bash
cd backend && pytest tests/test_image_schema.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/image.py backend/tests/test_image_schema.py
git commit -m "feat(schema): accept 'lama' as valid inpaint_method"
```

---

### Task 2: Добавить ленивый ONNX-загрузчик LaMa в `image_service`

**Goal:** Вспомогательная функция `_get_lama_session()` — скачивает `lama.onnx` при первом обращении, создаёт `onnxruntime.InferenceSession`, кеширует. Вторая функция `_inpaint_with_lama(image, mask)` — прогоняет LaMa по PIL-изображению и бинарной маске.

**Files:**
- Modify: `backend/app/services/image_service.py`
- Create: `backend/tests/test_image_inpaint.py` (пока два теста)

**Constants (добавить в модуль):**
```python
_LAMA_MODEL_URL = "https://huggingface.co/Carve/LaMa-ONNX/resolve/main/lama_fp32.onnx"
_LAMA_MODEL_SHA256 = ""  # TODO: заполнить после первого скачивания (используется для валидации кеша)
_LAMA_CACHE_DIR = Path.home() / ".cache" / "naturalskweb" / "lama"
_LAMA_CACHE_FILE = _LAMA_CACHE_DIR / "lama_fp32.onnx"
```

**Acceptance Criteria:**
- [ ] Глобальные `_lama_session` и `_lama_lock` объявлены на уровне модуля
- [ ] `_get_lama_session()` возвращает один и тот же `InferenceSession` при повторных вызовах (скачивание — только при первом)
- [ ] Файл кешируется в `~/.cache/naturalskweb/lama/lama_fp32.onnx`, при наличии файла сеть не дёргается
- [ ] Импорт `onnxruntime` и `urllib.request` — ленивые (внутри функции)
- [ ] `_inpaint_with_lama(pil_image, pil_mask)` возвращает PIL Image того же размера, что и вход
- [ ] Вход LaMa приводится к shape (1, 3, H, W) float32 [0..1]; маска — (1, 1, H, W) float32 [0/1]; H,W кратны 8 (pad справа/снизу)

**Verify:** `cd backend && pytest tests/test_image_inpaint.py -v` → PASS

**Steps:**

- [ ] **Step 1: Написать падающий тест лениво-кешированной сессии**

Создать `backend/tests/test_image_inpaint.py`:

```python
"""Unit tests for LaMa ONNX inference in image_service."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
from PIL import Image

from app.services import image_service


def test_lama_session_lazy_init(tmp_path, monkeypatch):
    """_get_lama_session returns same session across calls; download happens once."""
    image_service._lama_session = None  # reset cache

    fake_file = tmp_path / "lama.onnx"
    fake_file.write_bytes(b"fake onnx bytes")
    monkeypatch.setattr(image_service, "_LAMA_CACHE_FILE", fake_file)

    fake_session = MagicMock(name="InferenceSession")
    fake_ort = MagicMock(InferenceSession=MagicMock(return_value=fake_session))

    with patch.dict("sys.modules", {"onnxruntime": fake_ort}):
        first = image_service._get_lama_session()
        second = image_service._get_lama_session()

    assert first is fake_session
    assert second is fake_session
    assert fake_ort.InferenceSession.call_count == 1


def test_run_lama_onnx_preserves_shape(monkeypatch):
    """_run_lama_onnx returns a PIL image of the same size as input."""
    img = Image.new("RGB", (64, 48), color=(120, 200, 100))
    mask = Image.new("L", (64, 48), color=0)

    fake_output = np.full((1, 3, 48, 64), 255, dtype=np.float32)
    fake_session = MagicMock()
    fake_session.run.return_value = [fake_output]
    monkeypatch.setattr(image_service, "_get_lama_session", lambda: fake_session)

    result = image_service._run_lama_onnx(img, mask)

    assert isinstance(result, Image.Image)
    assert result.size == (64, 48)
    assert fake_session.run.call_count == 1
```

- [ ] **Step 2: Запустить тест — должен падать**

```bash
cd backend && pytest tests/test_image_inpaint.py -v
```

Expected: FAIL (AttributeError: `_lama_session` / `_get_lama_session` / `_run_lama_onnx`).

- [ ] **Step 3: Добавить LaMa-загрузчик в `image_service.py`**

После блока rembg (после `_get_rembg_session`) добавить:

```python
# ---------------------------------------------------------------------------
# Lazy-loaded LaMa ONNX model
# ---------------------------------------------------------------------------

_LAMA_MODEL_URL = "https://huggingface.co/Carve/LaMa-ONNX/resolve/main/lama_fp32.onnx"
_LAMA_CACHE_DIR = Path.home() / ".cache" / "naturalskweb" / "lama"
_LAMA_CACHE_FILE = _LAMA_CACHE_DIR / "lama_fp32.onnx"
_LAMA_PAD_MOD = 8  # LaMa input size must be divisible by 8

_lama_session = None
_lama_lock = threading.Lock()


def _download_lama_weights() -> None:
    """Download lama.onnx into cache on first access."""
    import urllib.request

    _LAMA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _LAMA_CACHE_FILE.with_suffix(".part")
    logger.info("Downloading LaMa weights from %s", _LAMA_MODEL_URL)
    urllib.request.urlretrieve(_LAMA_MODEL_URL, tmp)
    tmp.rename(_LAMA_CACHE_FILE)
    logger.info("LaMa weights saved to %s", _LAMA_CACHE_FILE)


def _get_lama_session():
    """Thread-safe lazy initialisation of the LaMa ONNX InferenceSession."""
    global _lama_session
    with _lama_lock:
        if _lama_session is None:
            import onnxruntime as ort

            if not _LAMA_CACHE_FILE.exists():
                _download_lama_weights()

            _lama_session = ort.InferenceSession(
                str(_LAMA_CACHE_FILE),
                providers=["CPUExecutionProvider"],
            )
            logger.info("LaMa ONNX session initialised")
        return _lama_session


def _pad_to_mod(arr: np.ndarray, mod: int) -> tuple[np.ndarray, int, int]:
    """Pad (H, W, ...) array on right/bottom so H and W are multiples of `mod`."""
    h, w = arr.shape[:2]
    ph = (mod - h % mod) % mod
    pw = (mod - w % mod) % mod
    if ph == 0 and pw == 0:
        return arr, 0, 0
    pad_width = [(0, ph), (0, pw)] + [(0, 0)] * (arr.ndim - 2)
    return np.pad(arr, pad_width, mode="edge"), ph, pw


def _run_lama_onnx(pil_image: Image.Image, pil_mask: Image.Image) -> Image.Image:
    """Run raw LaMa ONNX inference on (image, mask) and return result as PIL RGB.

    Low-level helper: no downsampling, no colour-space juggling. The wrapper
    `_inpaint_with_lama` in `_remove_watermark_sync` handles cv2↔PIL and resize.

    - pil_image: RGB of any size
    - pil_mask: L (grayscale), white = area to inpaint, black = keep
    """
    session = _get_lama_session()
    orig_w, orig_h = pil_image.size

    img_arr = np.array(pil_image.convert("RGB"), dtype=np.float32) / 255.0
    mask_arr = (np.array(pil_mask.convert("L"), dtype=np.float32) > 127).astype(np.float32)

    img_padded, ph, pw = _pad_to_mod(img_arr, _LAMA_PAD_MOD)
    mask_padded, _, _ = _pad_to_mod(mask_arr, _LAMA_PAD_MOD)

    img_tensor = np.transpose(img_padded, (2, 0, 1))[None, ...]         # (1, 3, H, W)
    mask_tensor = mask_padded[None, None, ...]                          # (1, 1, H, W)

    outputs = session.run(None, {"image": img_tensor, "mask": mask_tensor})
    out = outputs[0][0]                                                 # (3, H, W) or (H, W, 3)

    if out.shape[0] == 3:
        out = np.transpose(out, (1, 2, 0))
    out = out[: out.shape[0] - ph, : out.shape[1] - pw]                 # crop padding
    out = np.clip(out, 0.0, 255.0 if out.max() > 1.5 else 1.0)
    if out.max() <= 1.5:
        out = out * 255.0
    out = out.astype(np.uint8)

    result = Image.fromarray(out, mode="RGB")
    assert result.size == (orig_w, orig_h)
    return result
```

Убедиться, что `from pathlib import Path` и `import numpy as np` уже импортированы в модуле (иначе добавить).

- [ ] **Step 4: Запустить тесты — должны пройти**

```bash
cd backend && pytest tests/test_image_inpaint.py -v
```

Expected: PASS (оба теста).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/image_service.py backend/tests/test_image_inpaint.py
git commit -m "feat(image): add lazy LaMa ONNX loader and inference helper"
```

**Note:** Конкретные имена входов/выходов (`"image"`, `"mask"`) у модели `Carve/LaMa-ONNX` подтверждены её картой на HuggingFace. Если в рантайме они окажутся другими, имплементатор проверит через `session.get_inputs()` и скорректирует ключи.

---

### Task 3: Переработать `_remove_watermark_sync` — дилатация, радиус 10, LaMa-ветка

**Goal:** Все три метода (TELEA, NS, LaMa) корректно работают; маска дилатируется; для LaMa применяется даунсемплинг до 1536 px.

**Files:**
- Modify: `backend/app/services/image_service.py` (`_remove_watermark_sync`)
- Modify: `backend/tests/test_image_inpaint.py` (добавить ещё тесты)

**Acceptance Criteria:**
- [ ] `cv2.dilate` вызывается с эллиптическим ядром 11×11 до inpaint-а
- [ ] Для `telea` / `ns` `cv2.inpaint` получает `inpaintRadius=10`
- [ ] Для `lama` вызывается `_run_lama_onnx(pil_img, pil_mask)` через обёртку `_inpaint_with_lama`
- [ ] При размере входа > 1536 px по большей стороне изображение и маска даунсемплятся перед LaMa и апсемплятся обратно (LANCZOS)
- [ ] Результат сохраняется в `{uuid}.png`
- [ ] Превью результата создаётся (`_generate_preview`)

**Verify:** `cd backend && pytest tests/test_image_inpaint.py -v` → все тесты PASS

**Steps:**

- [ ] **Step 1: Написать падающие тесты — TELEA inpaintRadius=10 + дилатация**

В `backend/tests/test_image_inpaint.py` добавить импорты и helpers сверху (после существующих тестов `test_lama_session_lazy_init` / `test_run_lama_onnx_preserves_shape`):

```python
import os
import numpy as np
import pytest
from PIL import Image

from app.core.config import settings


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
```

Добавить `import cv2` в `image_service.py` на верхний уровень — чтобы `image_service.cv2` был атрибутом. **Важно:** OpenCV уже импортируется локально внутри `_remove_watermark_sync` (`import cv2`) — для возможности мокать через `patch.object(image_service.cv2, ...)` нужен импорт на уровне модуля. Если это мешает, можно оставить локальный импорт и в тестах использовать `patch("cv2.inpaint")` напрямую — выбрать при реализации, сохранив суть проверки.

- [ ] **Step 2: Запустить тесты — должны падать (дилатации нет, radius=3)**

```bash
cd backend && pytest tests/test_image_inpaint.py -v
```

Expected: 2 новых теста FAIL (radius=3, dilate не вызван).

- [ ] **Step 3: Переработать `_remove_watermark_sync`**

В `backend/app/services/image_service.py` заменить тело функции `_remove_watermark_sync` на:

```python
def _remove_watermark_sync(
    task_id: str,
    mask_shapes: list,
    inpaint_method: str,
) -> dict:
    """Synchronous watermark removal (runs in a worker thread).

    Routes to LaMa (deep learning, default) or OpenCV classical inpaint
    (TELEA / NS) based on inpaint_method. Mask is dilated by ~5 px before
    inpaint to be forgiving of imprecise user drawing.

    Returns dict with ``filename`` and ``file_size`` of the result.
    """
    import cv2
    import numpy as np

    task_dir = os.path.join(settings.UPLOAD_DIR, task_id)

    input_path = _find_input_file(task_dir)
    if input_path is None:
        raise FileNotFoundError(f"No input file found in {task_dir}")

    _update_status(task_id, "processing", progress=20.0)

    img = cv2.imread(input_path)
    if img is None:
        raise ValueError(f"Failed to read image: {input_path}")

    h, w = img.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)

    _update_status(task_id, "processing", progress=30.0)

    # Build mask from normalised shapes — additive shapes then erasers.
    def _get(shape, key, default=None):
        return shape.get(key, default) if isinstance(shape, dict) else getattr(shape, key, default)

    normal_shapes = [s for s in mask_shapes if not _get(s, "is_eraser", False)]
    eraser_shapes = [s for s in mask_shapes if _get(s, "is_eraser", False)]

    for shape in normal_shapes:
        shape_type = _get(shape, "type")
        points = _get(shape, "points")
        brush_size = _get(shape, "brush_size")

        if shape_type == "brush" and points:
            pts = np.array(
                [[int(p[0] * w), int(p[1] * h)] for p in points],
                dtype=np.int32,
            )
            thickness = max(1, int((brush_size or 0.02) * min(w, h)))
            cv2.polylines(mask, [pts], isClosed=False, color=255, thickness=thickness)

        elif shape_type == "rect" and len(points) >= 2:
            x1, y1 = int(points[0][0] * w), int(points[0][1] * h)
            x2, y2 = int(points[1][0] * w), int(points[1][1] * h)
            cv2.rectangle(mask, (x1, y1), (x2, y2), 255, -1)

    for shape in eraser_shapes:
        shape_type = _get(shape, "type")
        points = _get(shape, "points")
        brush_size = _get(shape, "brush_size")

        if shape_type == "brush" and points:
            pts = np.array(
                [[int(p[0] * w), int(p[1] * h)] for p in points],
                dtype=np.int32,
            )
            thickness = max(1, int((brush_size or 0.02) * min(w, h)))
            cv2.polylines(mask, [pts], isClosed=False, color=0, thickness=thickness)

    # Dilate mask by ~5 px — forgiving of imprecise user drawing, also
    # critical for LaMa: if the mask doesn't cover watermark boundaries,
    # artefacts remain.
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    mask = cv2.dilate(mask, kernel, iterations=1)

    _update_status(task_id, "processing", progress=50.0)

    if inpaint_method == "lama":
        result = _inpaint_with_lama(img, mask)
    else:
        flags = cv2.INPAINT_TELEA if inpaint_method == "telea" else cv2.INPAINT_NS
        result = cv2.inpaint(img, mask, 10, flags)

    _update_status(task_id, "processing", progress=80.0)

    result_name = f"{uuid.uuid4().hex}.png"
    result_path = os.path.join(task_dir, result_name)
    cv2.imwrite(result_path, result)

    file_size = os.path.getsize(result_path)

    _generate_preview(result_path, task_dir)

    _update_status(task_id, "processing", progress=95.0)

    return {"filename": result_name, "file_size": file_size}


def _inpaint_with_lama(img, mask):
    """Run LaMa inpainting, downsampling large inputs to stay within RAM.

    LaMa on CPU with 3000+ px images takes too long and risks OOM. Downsample
    to max 1536 px side, inpaint, then upsample result back using LANCZOS.
    """
    import cv2
    import numpy as np
    from PIL import Image

    MAX_LAMA_SIDE = 1536
    h, w = img.shape[:2]
    scale = min(MAX_LAMA_SIDE / max(h, w), 1.0)

    if scale < 1.0:
        new_w, new_h = int(w * scale), int(h * scale)
        img_for_lama = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        mask_for_lama = cv2.resize(mask, (new_w, new_h), interpolation=cv2.INTER_NEAREST)
    else:
        img_for_lama = img
        mask_for_lama = mask

    pil_img = Image.fromarray(cv2.cvtColor(img_for_lama, cv2.COLOR_BGR2RGB))
    pil_mask = Image.fromarray(mask_for_lama)

    result_pil = _run_lama_onnx(pil_img, pil_mask)

    if scale < 1.0:
        result_pil = result_pil.resize((w, h), Image.LANCZOS)

    return cv2.cvtColor(np.array(result_pil), cv2.COLOR_RGB2BGR)
```

- [ ] **Step 4: Запустить тесты TELEA/NS — должны пройти**

```bash
cd backend && pytest tests/test_image_inpaint.py::test_telea_uses_radius_10_and_dilates_mask tests/test_image_inpaint.py::test_ns_uses_radius_10 -v
```

Expected: PASS.

- [ ] **Step 5: Написать тест для LaMa-ветки**

В том же файле добавить:

```python
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

    # Result on disk retained original resolution (upsampled back)
    task_dir = os.path.join(settings.UPLOAD_DIR, large_task_dir)
    final = Image.open(os.path.join(task_dir, result["filename"]))
    assert final.size == (3000, 2000)
```

- [ ] **Step 6: Запустить все тесты в файле**

```bash
cd backend && pytest tests/test_image_inpaint.py -v
```

Expected: 5 passed (`test_lama_model_lazy_init`, два TELEA/NS, два LaMa).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/image_service.py backend/tests/test_image_inpaint.py
git commit -m "feat(image): add LaMa inpainting, mask dilation, radius 10 for classic methods"
```

---

### Task 4: Переключить rembg на `birefnet-general-lite` с alpha matting

**Goal:** Удаление фона использует более качественную модель и alpha matting для лучших краёв.

**Files:**
- Modify: `backend/app/services/image_service.py`

**Acceptance Criteria:**
- [ ] Константа `_REMBG_MODEL_NAME = "birefnet-general-lite"` определена на уровне модуля
- [ ] `_get_rembg_session()` использует эту константу
- [ ] `remove()` в `_remove_bg_sync` вызывается с `alpha_matting=True`, `alpha_matting_foreground_threshold=240`, `alpha_matting_background_threshold=10`, `alpha_matting_erode_size=10`, `post_process_mask=True`

**Verify:**
1. `cd backend && python -c "from app.services.image_service import _REMBG_MODEL_NAME; assert _REMBG_MODEL_NAME == 'birefnet-general-lite'; print('ok')"` → `ok`
2. Smoke-прогон (опционально): с тестовой картинкой проверить, что результат PNG-файл с альфа-каналом.

**Steps:**

- [ ] **Step 1: Изменить константу и сессию**

В `backend/app/services/image_service.py` заменить:

```python
_rembg_session = None
_rembg_lock = threading.Lock()


def _get_rembg_session():
    """Thread-safe lazy initialisation of the rembg u2netp session."""
    global _rembg_session
    with _rembg_lock:
        if _rembg_session is None:
            from rembg import new_session
            _rembg_session = new_session("u2netp")
            logger.info("rembg u2netp session initialised")
        return _rembg_session
```

на:

```python
_REMBG_MODEL_NAME = "birefnet-general-lite"
_rembg_session = None
_rembg_lock = threading.Lock()


def _get_rembg_session():
    """Thread-safe lazy initialisation of the rembg session."""
    global _rembg_session
    with _rembg_lock:
        if _rembg_session is None:
            from rembg import new_session
            _rembg_session = new_session(_REMBG_MODEL_NAME)
            logger.info("rembg %s session initialised", _REMBG_MODEL_NAME)
        return _rembg_session
```

- [ ] **Step 2: Обновить вызов `remove()` в `_remove_bg_sync`**

Найти в `_remove_bg_sync`:

```python
output_bytes = remove(input_bytes, session=session)
```

Заменить на:

```python
output_bytes = remove(
    input_bytes,
    session=session,
    alpha_matting=True,
    alpha_matting_foreground_threshold=240,
    alpha_matting_background_threshold=10,
    alpha_matting_erode_size=10,
    post_process_mask=True,
)
```

- [ ] **Step 3: Проверить константу**

```bash
cd backend && python -c "from app.services.image_service import _REMBG_MODEL_NAME; assert _REMBG_MODEL_NAME == 'birefnet-general-lite'; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Запустить бэкенд и сделать smoke-прогон (ручная проверка)**

```bash
cd backend && uvicorn app.main:app --reload
```

В отдельном терминале: открыть фронт, загрузить тестовую картинку (портрет или товар), выбрать удаление фона. Убедиться, что:
1. Модель скачалась (первый запуск) — проверить логи
2. Результат PNG с прозрачным фоном
3. Края объекта чистые, без грубых зазубрин

Если на 3.6 ГБ RAM вылетает OOM — понизить `_REMBG_MODEL_NAME = "isnet-general-use"` или убрать `alpha_matting=True`. Зафиксировать в коммит-сообщении, какой вариант применён.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/image_service.py
git commit -m "feat(image): switch rembg to birefnet-general-lite with alpha matting"
```

---

### Task 5: Прогрев моделей в `lifespan`

**Goal:** rembg и LaMa прогружаются в фоне при старте приложения, не блокируя его.

**Files:**
- Modify: `backend/app/main.py`

**Acceptance Criteria:**
- [ ] При старте приложения создаётся фоновый `asyncio.Task`, вызывающий `_get_rembg_session` и `_get_lama_session` через `asyncio.to_thread`
- [ ] Ошибка прогрева логируется через `logger.exception`, но не прерывает старт
- [ ] Приложение отвечает на `GET /health` сразу после старта (до завершения прогрева)

**Verify:** `cd backend && timeout 5 uvicorn app.main:app --port 8765 &` затем `curl -s http://localhost:8765/health` → `{"status":"ok"}`

**Steps:**

- [ ] **Step 1: Изменить lifespan**

В `backend/app/main.py`, в функции `lifespan`, сразу после `logger.info("NaturalskWeb backend started")` и перед `yield`, добавить:

```python
    async def _warmup_image_models():
        from app.services import image_service
        try:
            await asyncio.to_thread(image_service._get_rembg_session)
            await asyncio.to_thread(image_service._get_lama_session)
            logger.info("Image models warmed up")
        except Exception:
            logger.exception("Image models warmup failed")

    import asyncio
    asyncio.create_task(_warmup_image_models())
```

Предпочтительно `import asyncio` вынести в верх файла, если его там ещё нет (проверить).

- [ ] **Step 2: Ручная проверка**

```bash
cd backend && uvicorn app.main:app --port 8765 &
sleep 2
curl -s http://localhost:8765/health
kill %1
```

Expected: `{"status":"ok"}` — приложение отвечает сразу, прогрев в логах виден («rembg birefnet-general-lite session initialised», «LaMa ONNX session initialised», «Image models warmed up»). При первом запуске дополнительно логируется скачивание весов LaMa (~200 МБ).

- [ ] **Step 3: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(image): warm up rembg and LaMa models on startup"
```

---

### Task 6: Frontend — расширить тип `InpaintMethod`

**Goal:** TypeScript-тип принимает `'lama'`.

**Files:**
- Modify: `frontend/src/pages/ImageProcessor/types.ts`

**Acceptance Criteria:**
- [ ] `InpaintMethod = 'lama' | 'telea' | 'ns'`

**Verify:** `cd frontend && bun run build` → пройдёт без ошибок (при условии, что Task 7 уже сделан; если делать в правильном порядке — build падёт на этом шаге, это нормально, исправится в Task 7).

**Steps:**

- [ ] **Step 1: Изменить тип**

В `frontend/src/pages/ImageProcessor/types.ts` заменить:

```ts
export type InpaintMethod = 'telea' | 'ns'
```

на:

```ts
export type InpaintMethod = 'lama' | 'telea' | 'ns'
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/ImageProcessor/types.ts
git commit -m "feat(types): add 'lama' to InpaintMethod union"
```

---

### Task 7: Frontend — обновить `WatermarkRemoval.tsx`

**Goal:** Дефолтный метод `lama`, читаемые подписи опций, подсказка под селектом, сообщение о длительности.

**Files:**
- Modify: `frontend/src/pages/ImageProcessor/components/WatermarkRemoval.tsx`
- Modify: `frontend/src/pages/ImageProcessor/components/WatermarkRemoval.module.css`

**Acceptance Criteria:**
- [ ] `useState<InpaintMethod>('lama')` (было `'telea'`)
- [ ] Три `<option>`: `"LaMa (нейросеть, рекомендуется)"`, `"TELEA (быстрый классический)"`, `"Navier-Stokes (классический)"`
- [ ] Под селектом — одна строка-подсказка в стиле `--text-secondary`, `--fs-xs`
- [ ] В фазе `processing`, если выбран `lama`, под прогрессбаром — «LaMa работает локально на CPU и может занять до минуты.»

**Verify:** `cd frontend && bun run lint && bun run build` → без ошибок. Визуально — открыть фронт, перейти на вкладку «Удаление водяных знаков», проверить дефолтный селект и подсказку.

**Steps:**

- [ ] **Step 1: Изменить `useState`**

В `WatermarkRemoval.tsx` заменить:

```ts
const [inpaintMethod, setInpaintMethod] = useState<InpaintMethod>('telea')
```

на:

```ts
const [inpaintMethod, setInpaintMethod] = useState<InpaintMethod>('lama')
```

- [ ] **Step 2: Обновить селект и добавить подсказку**

Заменить блок:

```tsx
<select
  className={styles.methodSelect}
  value={inpaintMethod}
  onChange={(e) => setInpaintMethod(e.target.value as InpaintMethod)}
  title="Метод инпейнтинга"
>
  <option value="telea">TELEA</option>
  <option value="ns">Navier-Stokes</option>
</select>
```

на:

```tsx
<div className={styles.methodWrap}>
  <select
    className={styles.methodSelect}
    value={inpaintMethod}
    onChange={(e) => setInpaintMethod(e.target.value as InpaintMethod)}
    title="Метод инпейнтинга"
  >
    <option value="lama">LaMa (нейросеть, рекомендуется)</option>
    <option value="telea">TELEA (быстрый классический)</option>
    <option value="ns">Navier-Stokes (классический)</option>
  </select>
  <p className={styles.methodHint}>
    LaMa даёт лучший результат для крупных и сложных знаков.
    Классические методы работают быстрее на мелких дефектах.
  </p>
</div>
```

- [ ] **Step 3: Добавить текст длительности в фазе `processing`**

Найти в том же файле блок:

```tsx
{phase === 'processing' && (
  <div className={styles.processingSection}>
    <Loader2 size={32} className={styles.iconSpin} aria-hidden="true" />
    <p className={styles.processingText}>Обработка... {progress}%</p>
    <div className={styles.progressBarWrap}>
      <div
        className={styles.progressBarFill}
        style={{ width: `${progress}%` }}
      />
    </div>
  </div>
)}
```

Добавить подсказку после прогрессбара:

```tsx
{phase === 'processing' && (
  <div className={styles.processingSection}>
    <Loader2 size={32} className={styles.iconSpin} aria-hidden="true" />
    <p className={styles.processingText}>Обработка... {progress}%</p>
    <div className={styles.progressBarWrap}>
      <div
        className={styles.progressBarFill}
        style={{ width: `${progress}%` }}
      />
    </div>
    {inpaintMethod === 'lama' && (
      <p className={styles.processingHint}>
        LaMa работает локально на CPU и может занять до минуты.
      </p>
    )}
  </div>
)}
```

- [ ] **Step 4: Добавить CSS-классы**

В `WatermarkRemoval.module.css` добавить в конец файла:

```css
.methodWrap {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  flex: 1;
  min-width: 0;
}

.methodHint {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  line-height: 1.4;
}

.processingHint {
  margin: var(--space-2) 0 0;
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  text-align: center;
}
```

- [ ] **Step 5: Проверить lint и сборку**

```bash
cd frontend && bun run lint && bun run build
```

Expected: без ошибок.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/ImageProcessor/components/WatermarkRemoval.tsx \
        frontend/src/pages/ImageProcessor/components/WatermarkRemoval.module.css
git commit -m "feat(ui): default to LaMa inpainting with hint and duration notice"
```

---

### Task 8: Frontend — переработать `ImageCompare.tsx`

**Goal:** Три режима (До / Сравнить / После), инвертированная семантика шторки (слева = «До»), клавиатурная навигация, шашечка прозрачности.

**Files:**
- Modify: `frontend/src/pages/ImageProcessor/components/ImageCompare.tsx`
- Modify: `frontend/src/pages/ImageProcessor/components/ImageCompare.module.css`

**Acceptance Criteria:**
- [ ] Компонент принимает новый prop `transparencyGrid?: boolean`
- [ ] Состояние `mode: 'before' | 'compare' | 'after'`, дефолт `'compare'`
- [ ] Над изображением — сегментированный переключатель режимов с иконками lucide
- [ ] В режиме `compare`: фоновый слой — `afterSrc`, верхний клипованный слой — `beforeSrc` (ширина = `position%`). Лейблы «До» сверху-слева, «После» сверху-справа.
- [ ] В режимах `before` / `after`: только одна картинка на всю область; лейбл «До» или «После» в верхнем левом углу.
- [ ] Ручка слайдера: `role="slider"`, `tabIndex={0}`, `aria-valuenow`, обработка клавиш `←/→` (±2%), `Shift+←/→` (±10%), `Home` (0), `End` (100).
- [ ] При `transparencyGrid=true` в контейнере виден клетчатый фон.
- [ ] `BackgroundRemoval.tsx` передаёт `transparencyGrid={true}` (см. Task 9).

**Verify:** `cd frontend && bun run lint && bun run build` → без ошибок. Визуально — открыть обе вкладки, проверить все три режима, клавиатуру, шашечку на удалении фона.

**Steps:**

- [ ] **Step 1: Переписать `ImageCompare.tsx`**

Заменить содержимое `frontend/src/pages/ImageProcessor/components/ImageCompare.tsx`:

```tsx
// ── ImageCompare — before/after comparison with three modes ──
//
// Modes: 'before' (show original only), 'compare' (draggable shutter),
// 'after' (show result only). In 'compare' mode the left half shows
// the original ("До"), right half shows the result ("После"), matching
// conventional visual comparison.

import { useRef, useState, useCallback } from 'react'
import { Eye, Columns2, Sparkles } from 'lucide-react'
import styles from './ImageCompare.module.css'

type CompareMode = 'before' | 'compare' | 'after'

interface ImageCompareProps {
  beforeSrc: string
  afterSrc: string
  beforeLabel?: string
  afterLabel?: string
  transparencyGrid?: boolean
}

export function ImageCompare({
  beforeSrc,
  afterSrc,
  beforeLabel = 'До',
  afterLabel = 'После',
  transparencyGrid = false,
}: ImageCompareProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [mode, setMode] = useState<CompareMode>('compare')
  const [position, setPosition] = useState(50)
  const isDragging = useRef(false)

  const updatePosition = useCallback((clientX: number) => {
    const container = containerRef.current
    if (!container) return
    const rect = container.getBoundingClientRect()
    const x = clientX - rect.left
    const pct = Math.max(0, Math.min(100, (x / rect.width) * 100))
    setPosition(pct)
  }, [])

  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (mode !== 'compare') return
      isDragging.current = true
      ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
      updatePosition(e.clientX)
    },
    [mode, updatePosition],
  )

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!isDragging.current) return
      updatePosition(e.clientX)
    },
    [updatePosition],
  )

  const handlePointerUp = useCallback(() => {
    isDragging.current = false
  }, [])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    const big = e.shiftKey ? 10 : 2
    if (e.key === 'ArrowLeft') {
      e.preventDefault()
      setPosition((p) => Math.max(0, p - big))
    } else if (e.key === 'ArrowRight') {
      e.preventDefault()
      setPosition((p) => Math.min(100, p + big))
    } else if (e.key === 'Home') {
      e.preventDefault()
      setPosition(0)
    } else if (e.key === 'End') {
      e.preventDefault()
      setPosition(100)
    }
  }, [])

  const containerClass = [
    styles.container,
    transparencyGrid ? styles.grid : '',
    mode === 'compare' ? styles.cursorCompare : '',
  ].filter(Boolean).join(' ')

  return (
    <div className={styles.wrap}>
      {/* Mode switcher */}
      <div className={styles.modeSwitcher} role="radiogroup" aria-label="Режим сравнения">
        <button
          type="button"
          role="radio"
          aria-checked={mode === 'before'}
          className={mode === 'before' ? styles.modeBtnActive : styles.modeBtn}
          onClick={() => setMode('before')}
        >
          <Eye size={14} aria-hidden="true" />
          Только {beforeLabel.toLowerCase()}
        </button>
        <button
          type="button"
          role="radio"
          aria-checked={mode === 'compare'}
          className={mode === 'compare' ? styles.modeBtnActive : styles.modeBtn}
          onClick={() => setMode('compare')}
        >
          <Columns2 size={14} aria-hidden="true" />
          Сравнить
        </button>
        <button
          type="button"
          role="radio"
          aria-checked={mode === 'after'}
          className={mode === 'after' ? styles.modeBtnActive : styles.modeBtn}
          onClick={() => setMode('after')}
        >
          <Sparkles size={14} aria-hidden="true" />
          Только {afterLabel.toLowerCase()}
        </button>
      </div>

      {/* Image area */}
      <div
        ref={containerRef}
        className={containerClass}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
      >
        {mode === 'before' && (
          <>
            <img src={beforeSrc} alt={beforeLabel} className={styles.image} draggable={false} />
            <span className={`${styles.label} ${styles.labelTopLeft}`}>{beforeLabel}</span>
          </>
        )}

        {mode === 'after' && (
          <>
            <img src={afterSrc} alt={afterLabel} className={styles.image} draggable={false} />
            <span className={`${styles.label} ${styles.labelTopLeft}`}>{afterLabel}</span>
          </>
        )}

        {mode === 'compare' && (
          <>
            {/* After as background */}
            <img src={afterSrc} alt={afterLabel} className={styles.image} draggable={false} />

            {/* Before clipped from the left by wrapper width */}
            <div className={styles.beforeWrapper} style={{ width: `${position}%` }}>
              <img src={beforeSrc} alt={beforeLabel} className={styles.image} draggable={false} />
            </div>

            {/* Labels in top corners */}
            <span className={`${styles.label} ${styles.labelTopLeft}`}>{beforeLabel}</span>
            <span className={`${styles.label} ${styles.labelTopRight}`}>{afterLabel}</span>

            {/* Slider handle */}
            <div className={styles.slider} style={{ left: `${position}%` }}>
              <div className={styles.sliderLine} />
              <div
                className={styles.sliderHandle}
                role="slider"
                tabIndex={0}
                aria-label="Позиция сравнения"
                aria-valuenow={Math.round(position)}
                aria-valuemin={0}
                aria-valuemax={100}
                onKeyDown={handleKeyDown}
              >
                <svg width="14" height="14" viewBox="0 0 12 12" aria-hidden="true">
                  <path d="M3 1L0 6l3 5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M9 1l3 5-3 5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Переписать `ImageCompare.module.css`**

Заменить содержимое `frontend/src/pages/ImageProcessor/components/ImageCompare.module.css`:

```css
/* ── ImageCompare styles ── */

.wrap {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

/* ── Mode switcher ── */
.modeSwitcher {
  display: inline-flex;
  align-self: center;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 4px;
  gap: 2px;
}

.modeBtn,
.modeBtnActive {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-family: var(--font-ui);
  font-size: var(--fs-xs);
  font-weight: 600;
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: background var(--transition-fast), color var(--transition-fast);
}

.modeBtn:hover {
  color: var(--text-primary);
}

.modeBtnActive {
  background: var(--bg-card);
  color: var(--text-primary);
  box-shadow: var(--shadow-sm);
}

/* ── Image container ── */
.container {
  position: relative;
  overflow: hidden;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  background: var(--bg-secondary);
  user-select: none;
  touch-action: none;
  line-height: 0;
  container-type: inline-size;
}

.cursorCompare {
  cursor: ew-resize;
}

/* Transparency checker grid — for PNG with alpha channel */
.grid {
  background-color: #2a2a32;
  background-image:
    linear-gradient(45deg, #3a3a44 25%, transparent 25%),
    linear-gradient(-45deg, #3a3a44 25%, transparent 25%),
    linear-gradient(45deg, transparent 75%, #3a3a44 75%),
    linear-gradient(-45deg, transparent 75%, #3a3a44 75%);
  background-size: 16px 16px;
  background-position: 0 0, 0 8px, 8px -8px, -8px 0px;
}

.image {
  display: block;
  width: 100%;
  height: auto;
  object-fit: contain;
  pointer-events: none;
}

/* Before wrapper — clips from the left by controlling width */
.beforeWrapper {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  overflow: hidden;
}

.beforeWrapper .image {
  /* Match container width so image doesn't squash as wrapper shrinks */
  width: 100cqw;
  min-width: 0;
}

/* ── Labels ── */
.label {
  position: absolute;
  top: var(--space-3);
  padding: var(--space-1) var(--space-3);
  font-family: var(--font-ui);
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--text-primary);
  background: rgba(10, 10, 15, 0.75);
  border-radius: var(--radius-sm);
  pointer-events: none;
  backdrop-filter: blur(4px);
}

.labelTopLeft {
  left: var(--space-3);
}

.labelTopRight {
  right: var(--space-3);
}

/* ── Slider line + handle ── */
.slider {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 0;
  transform: translateX(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  pointer-events: none;
}

.sliderLine {
  flex: 1;
  width: 2px;
  background: var(--text-primary);
  box-shadow: 0 0 4px rgba(0, 0, 0, 0.5);
}

.sliderHandle {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 40px;
  height: 40px;
  border-radius: var(--radius-full);
  background: var(--bg-card);
  border: 2px solid var(--text-primary);
  box-shadow: var(--shadow-md);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-primary);
  pointer-events: auto;
  cursor: ew-resize;
  outline: none;
  transition:
    border-color var(--transition-fast),
    box-shadow var(--transition-fast);
}

.sliderHandle:hover,
.sliderHandle:focus-visible {
  border-color: var(--accent);
  box-shadow: var(--shadow-glow);
}

/* ── Responsive ── */
@media (max-width: 480px) {
  .sliderHandle {
    width: 32px;
    height: 32px;
  }

  .label {
    font-size: 0.625rem;
    padding: 2px var(--space-2);
  }

  .modeBtn,
  .modeBtnActive {
    padding: var(--space-1) var(--space-2);
  }
}
```

- [ ] **Step 3: Проверить lint и сборку**

```bash
cd frontend && bun run lint && bun run build
```

Expected: без ошибок.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ImageProcessor/components/ImageCompare.tsx \
        frontend/src/pages/ImageProcessor/components/ImageCompare.module.css
git commit -m "feat(ui): redesign ImageCompare with three modes and correct semantics"
```

---

### Task 9: Frontend — включить шашечку прозрачности в `BackgroundRemoval`

**Goal:** Результат удаления фона отображается на клетчатом фоне, подчёркивая прозрачные области.

**Files:**
- Modify: `frontend/src/pages/ImageProcessor/components/BackgroundRemoval.tsx`

**Acceptance Criteria:**
- [ ] `<ImageCompare ... transparencyGrid={true} />` в фазе `result`

**Verify:** `cd frontend && bun run build` → без ошибок. Визуально — удалить фон на тестовой картинке и увидеть шашечку там, где прозрачно.

**Steps:**

- [ ] **Step 1: Передать prop**

В `BackgroundRemoval.tsx` заменить:

```tsx
<ImageCompare beforeSrc={previewUrl} afterSrc={resultPreviewUrl} />
```

на:

```tsx
<ImageCompare
  beforeSrc={previewUrl}
  afterSrc={resultPreviewUrl}
  transparencyGrid={true}
/>
```

- [ ] **Step 2: Проверить сборку**

```bash
cd frontend && bun run build
```

Expected: без ошибок.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ImageProcessor/components/BackgroundRemoval.tsx
git commit -m "feat(ui): show transparency grid in background removal result"
```

---

### Task 10: Финальная верификация

**Goal:** Все тесты/линты проходят, конечный UX проверен вручную.

**Files:**
- Нет изменений кода

**Acceptance Criteria:**
- [ ] `pytest` в backend — все тесты PASS
- [ ] `bun run lint` в frontend — без ошибок
- [ ] `bun run build` в frontend — успех
- [ ] Ручной прогон: удаление фона (портрет + товарное фото) — результаты визуально значительно лучше, чем с u2netp
- [ ] Ручной прогон: удаление крупного водяного знака с LaMa — без видимых артефактов; с TELEA — артефакты меньше, чем были (радиус 10 + дилатация)
- [ ] UI сравнения: все три режима работают, слева «До», справа «После», клавиатура работает, шашечка видна только для удаления фона

**Verify:**
1. `cd backend && pytest -v`
2. `cd frontend && bun run lint && bun run build`
3. Ручная проверка страницы Image Processor с реальными картинками.

**Steps:**

- [ ] **Step 1: Запустить backend-тесты**

```bash
cd backend && pytest -v
```

Expected: все тесты PASS.

- [ ] **Step 2: Запустить frontend lint + build**

```bash
cd frontend && bun run lint && bun run build
```

Expected: без ошибок.

- [ ] **Step 3: Поднять dev-окружение и проверить вручную**

Два терминала:

```bash
# Terminal 1
cd backend && uvicorn app.main:app --reload
```

```bash
# Terminal 2
cd frontend && bun run dev
```

Открыть `http://localhost:5173`, залогиниться, перейти в Image Processor.

Прогнать:
1. Удаление фона — портрет с волосами и товарное фото. Результат должен быть заметно лучше текущего (на глаз — края чёткие, волосы прорисованы).
2. Удаление водяного знака — загрузить картинку с явным диагональным текстом, обвести его кистью, обработать с методом LaMa. Знак должен исчезнуть практически без следов.
3. Тот же знак с TELEA — должен быть лучше, чем раньше (дилатация + радиус 10), но заметно хуже LaMa.
4. UI сравнения: переключить все три режима; клавиатурой (Tab → стрелки) подвигать ручку; убедиться, что шашечка видна на результате удаления фона и не видна в watermark.

- [ ] **Step 4: При необходимости — финальный коммит с настройками**

Если в процессе обнаружен OOM по BiRefNet-lite или другие тонкие правки — зафиксировать отдельным коммитом с понятным сообщением (например, `fix(image): fall back to isnet-general-use on memory-constrained host`).

---

## Self-review checklist (для писавшего план)

- Нет плейсхолдеров «TBD» / «добавить обработку ошибок» — все шаги содержат код
- Все файлы, упомянутые в File Structure, покрыты задачами
- Типы/сигнатуры согласованы: `_get_lama_session`, `_run_lama_onnx`, `_inpaint_with_lama` (обёртка), `InpaintMethod`, `ImageCompareProps.transparencyGrid` — используются одинаково во всех задачах
- Зависимости задач понятны: Task 0 → 2, 4; Task 1 → 3; Task 2 → 3; Task 6 → 7, 8; Task 8 → 9
- Риски из спеки (OOM BiRefNet-lite, размер весов LaMa ONNX ~200 МБ) — упомянуты в Task 0 и Task 4 с планом отката
