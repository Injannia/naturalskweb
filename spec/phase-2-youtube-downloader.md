# Фаза 2 — YouTube Downloader (Загрузчик видео)

> Цель: реализовать загрузку видео и плейлистов с YouTube с выбором качества и формата.

---

## 🔧 Backend

### 2.1 Зависимости
- [ ] Добавить `yt-dlp` в `requirements.txt`
- [ ] Убедиться что FFmpeg доступен в системе (для конвертации mp3/wav)

### 2.2 Pydantic схемы (`app/schemas/youtube.py`)

```python
class VideoInfoRequest:
    url: str  # URL видео или плейлиста

class VideoFormat:
    format_id: str
    ext: str           # mp4, webm
    resolution: str    # 1080p, 720p, 480p, 360p
    filesize: int | None
    fps: int | None
    vcodec: str
    acodec: str

class VideoInfo:
    id: str
    title: str
    thumbnail: str
    duration: int  # секунды
    channel: str
    upload_date: str
    formats: list[VideoFormat]

class PlaylistInfo:
    id: str
    title: str
    channel: str
    video_count: int
    videos: list[VideoInfo]

class DownloadRequest:
    url: str
    video_ids: list[str] | None  # если None — скачать всё
    format: str  # 'mp4', 'mp3', 'wav'
    quality: str  # 'best', '1080p', '720p', '480p', '360p'

class DownloadStatus:
    task_id: str
    status: str  # 'pending', 'downloading', 'converting', 'ready', 'error'
    progress: float  # 0.0 - 100.0
    filename: str | None
    error: str | None
    download_url: str | None
```

### 2.3 Сервис (`app/services/youtube_service.py`)

#### Методы:

**`get_video_info(url: str) -> VideoInfo | PlaylistInfo`**
- Использовать `yt-dlp` с `extract_flat=True` для плейлистов
- Извлекать доступные форматы, заголовок, thumbnail, длительность
- Фильтровать форматы: оставить только 360p, 480p, 720p, 1080p
- Timeout: 30 секунд

**`download_video(request: DownloadRequest, task_id: str) -> str`**
- Запускается как background task
- Скачивание через yt-dlp с прогресс-колбэком
- Сохранение в `uploads/{task_id}/`
- Обновление прогресса в in-memory dict
- Конвертация в нужный формат:
  - `mp4` → скачать как mp4 (merge best video+audio через yt-dlp)
  - `mp3` → скачать аудио и конвертировать через FFmpeg в mp3
  - `wav` → скачать аудио и конвертировать через FFmpeg в wav
- Для плейлистов: создать ZIP с выбранными видео

**`get_download_progress(task_id: str) -> DownloadStatus`**
- Возвращает текущий статус и прогресс загрузки

#### Хранение прогресса:
```python
# In-memory dict для отслеживания прогресса
_download_tasks: dict[str, DownloadStatus] = {}
```

### 2.4 API роутер (`app/routers/youtube.py`)

| Метод | URL | Описание | Auth |
|-------|-----|---------|------|
| POST | `/api/youtube/info` | Получить инфо о видео/плейлисте | ✅ |
| POST | `/api/youtube/download` | Начать загрузку | ✅ |
| GET  | `/api/youtube/status/{task_id}` | Статус загрузки | ✅ |
| GET  | `/api/youtube/file/{task_id}` | Скачать готовый файл | ✅ |
| DELETE | `/api/youtube/cancel/{task_id}` | Отменить загрузку | ✅ |

#### Ограничения:
- Проверка permission `youtube` у пользователя
- Проверка дневного лимита
- Максимальный размер плейлиста: 50 видео
- Максимальная длительность видео: 4 часа

### 2.5 Обработка ошибок
- URL не является YouTube ссылкой → `400 Bad Request`
- Видео недоступно (приватное, удалённое) → `404 Not Found`
- Превышен лимит → `429 Too Many Requests`
- Ошибка yt-dlp → `500 Internal Server Error` + детали в логах
- Timeout при получении инфо → `408 Request Timeout`

---

## 🎨 Frontend

### 2.6 Страница YouTube (`src/pages/YouTube/`)

#### Компоненты:

**`YouTubePage.tsx`** — основная страница
- Поле ввода URL (с валидацией YouTube ссылки)
- Кнопка "Получить информацию"
- Секция с результатами
- Список активных загрузок

**`VideoCard.tsx`** — карточка видео
- Thumbnail (превью)
- Название видео
- Канал, длительность
- Чекбокс для выбора (в плейлисте)

**`PlaylistView.tsx`** — отображение плейлиста
- Заголовок плейлиста
- Кнопки "Выбрать все" / "Снять все"
- Список VideoCard с чекбоксами
- Счётчик выбранных: "5 из 20 видео"

**`DownloadOptions.tsx`** — настройки загрузки
- Выбор формата: mp4 / mp3 / wav (toggle buttons)
- Выбор качества: dropdown (360p, 480p, 720p, 1080p, Best)
  - Для mp3/wav качество не показывается
- Кнопка "Скачать"

**`DownloadProgress.tsx`** — прогресс загрузки
- Progress bar с процентами
- Статус: Скачивание... / Конвертация... / Готово
- Размер файла
- Кнопка "Скачать файл" (при готовности)
- Кнопка "Отменить"

#### UX-flow:
```
1. Вставить YouTube URL → [Получить информацию]
2. Загрузка инфо (spinner)
3. Показать карточку видео / список плейлиста
4. Выбрать видео (для плейлиста)
5. Выбрать формат (mp4/mp3/wav) и качество
6. [Скачать] → Progress bar
7. Статус обновляется через polling каждые 2 секунды
8. [Скачать файл] → ответ от сервера в виде файла
```

### 2.7 Стилизация
- Военно-чёрный стиль с карточками
- Thumbnail с закруглёнными углами
- Progress bar в стиле accent цвета (синий)
- Мобильная адаптация: карточки в колонку

### 2.8 Валидация на клиенте
- URL должен содержать `youtube.com` или `youtu.be`
- Показывать ошибку если URL невалидный
- Disabled кнопка "Скачать" пока не выбраны видео/формат

---

## ✅ Критерии завершения Phase 2

- [ ] Можно вставить URL видео и получить информацию (title, thumbnail, форматы)
- [ ] Можно вставить URL плейлиста и увидеть список видео
- [ ] Можно выбрать формат (mp4/mp3/wav) и качество и начать загрузку
- [ ] Progress bar показывает реальный прогресс
- [ ] Можно скачать готовый файл
- [ ] Плейлист скачивается как ZIP
- [ ] Лимиты пользователя учитываются
- [ ] Мобильная версия работает корректно
