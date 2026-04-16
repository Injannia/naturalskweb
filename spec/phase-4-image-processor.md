# Фаза 4 — Image Processor (Обработка изображений)

> Цель: удаление фона и водяных знаков с фотографий с помощью локальных AI-моделей (оптимизировано для слабого железа).

---

## 🔧 Backend

### 4.1 Зависимости
```
rembg[cpu]>=2.0.50     # Лёгкая модель u2netp для слабого железа
opencv-python-headless>=4.8.0
numpy>=1.24.0
Pillow>=10.0.0
```

### 4.2 Два режима обработки

**Режим 1: Удаление фона (rembg)**
- Использовать модель `u2netp` (лёгкая, ~4MB vs ~176MB у u2net)
- Загрузить модель при старте приложения (один раз)
- Вход: изображение (jpg, png, webp)
- Выход: PNG с прозрачным фоном

**Режим 2: Удаление водяных знаков (OpenCV + Pillow)**
- Пользователь отмечает область кистью или прямоугольником
- Inpainting через OpenCV (`cv2.inpaint` метод TELEA или NS)
- Вход: изображение + маска (координаты отмеченных областей)
- Выход: обработанное изображение

### 4.3 Схемы (`app/schemas/image.py`)

```python
class ImageUploadResponse:
    task_id: str
    filename: str
    width: int
    height: int
    preview_url: str        # URL превью

class RemoveBackgroundRequest:
    task_id: str

class WatermarkArea:
    type: str              # 'brush' или 'rect'
    points: list[dict]     # [{x, y, radius}] для кисти или [{x1,y1,x2,y2}] для rect

class RemoveWatermarkRequest:
    task_id: str
    areas: list[WatermarkArea]
    method: str            # 'telea' или 'ns' (navier-stokes)

class ImageProcessResult:
    task_id: str
    status: str            # 'processing', 'ready', 'error'
    preview_url: str | None
    download_url: str | None
    error: str | None
```

### 4.4 Сервис (`app/services/image_service.py`)

**`remove_background(input_path) -> str`**
- Загрузить изображение через Pillow
- Вызвать `rembg.remove()` с моделью `u2netp`
- Сохранить результат как PNG
- Создать preview (уменьшенное)

**`remove_watermark(input_path, areas, method) -> str`**
- Загрузить через OpenCV
- Создать маску из отмеченных областей
- Для `brush`: нарисовать круги по точкам с заданным радиусом
- Для `rect`: залить прямоугольные области
- Применить `cv2.inpaint(img, mask, inpaintRadius=3, flags=method)`
- Сохранить результат

**`create_preview(image_path, max_size=800) -> str`**
- Уменьшить до max 800px по большей стороне
- Сохранить как JPEG quality=85

### 4.5 API роутер (`app/routers/image.py`)

| Метод | URL | Описание |
|-------|-----|---------|
| POST | `/api/image/upload` | Загрузить изображение |
| GET | `/api/image/preview/{task_id}` | Получить превью |
| POST | `/api/image/remove-bg` | Удалить фон |
| POST | `/api/image/remove-watermark` | Удалить водяной знак |
| GET | `/api/image/status/{task_id}` | Статус обработки |
| GET | `/api/image/result/{task_id}` | Скачать результат |
| GET | `/api/image/preview-result/{task_id}` | Превью результата |

Ограничения: макс 20MB на файл, только jpg/png/webp/bmp/tiff.

---

## 🎨 Frontend

### 4.6 Страница (`src/pages/ImageProcessor/`)

**`ImageProcessorPage.tsx`** — табы: "Удаление фона" / "Удаление водяных знаков"

**`ImageUploader.tsx`** — drag-and-drop + preview загруженного изображения

**`BackgroundRemover.tsx`**
- Показать оригинал слева, результат справа (split view)
- Кнопка "Удалить фон" с loading
- Сравнение Before/After со слайдером
- Кнопка скачать результат (PNG)

**`WatermarkRemover.tsx`**
- Canvas поверх изображения для рисования
- Панель инструментов: Кисть (с настройкой размера) / Прямоугольник / Ластик
- Выбор метода: TELEA / Navier-Stokes
- Кнопка "Обработать" → показать результат
- Before/After сравнение
- Кнопка "Отменить" (undo последнее действие)

**`ImageCompare.tsx`** — Before/After слайдер сравнения

### 4.7 UX-flow

**Удаление фона:**
```
1. Drag-and-drop изображение
2. Превью оригинала
3. [Удалить фон] → спиннер (5-15 сек)
4. Before/After сравнение
5. [Скачать PNG]
```

**Удаление водяных знаков:**
```
1. Drag-and-drop изображение
2. Превью на canvas
3. Выбрать инструмент (кисть/прямоугольник)
4. Отметить области водяного знака
5. [Обработать] → результат
6. Before/After → [Скачать]
```

---

## ✅ Критерии завершения
- [ ] Удаление фона работает (rembg u2netp)
- [ ] Удаление водяных знаков кистью и прямоугольником
- [ ] Before/After сравнение со слайдером
- [ ] Canvas рисование работает на мобильных (touch events)
- [ ] Обработка одного фото < 15 секунд на слабом железе
