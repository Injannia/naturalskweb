# Фаза 3 — File Converter (Мульти-конвертер файлов)

> Цель: конвертация медиа-файлов и документов с детальными настройками.

---

## 🔧 Backend

### 3.1 Зависимости
- `Pillow>=10.0.0` в requirements.txt
- FFmpeg 6.x+ (системная зависимость — уже используется YouTube Downloader)
- LibreOffice 7.x+ headless (системная зависимость для документов)

### 3.2 Поддерживаемые форматы

| Категория | Вход | Выход | Движок |
|-----------|------|-------|--------|
| Видео | mp4, avi, mkv, mov, wmv, flv, webm | mp4, avi, mkv, mov, webm | FFmpeg |
| Аудио | mp3, wav, ogg, flac, aac, wma, m4a | mp3, wav, ogg, flac, aac | FFmpeg |
| Изображения | jpg/jpeg, png, bmp, tiff, webp, gif, ico | jpg, png, bmp, tiff, webp, gif, ico | Pillow |
| Документы | docx, doc, odt, rtf, txt, xlsx, xls, csv, pptx, ppt | pdf, docx, odt, txt, html, xlsx, csv | LibreOffice |

### 3.3 Модель данных (`app/models/convert_task.py`)

Таблица `convert_tasks` — отдельная от `download_tasks` (YouTube), без кэширования.

| Поле | Тип | Описание |
|------|-----|----------|
| id | String(36) PK | UUID задачи |
| user_id | Integer FK | Владелец |
| batch_id | String(36) nullable, indexed | Группировка пакетных конвертаций |
| status | String(20) | pending → uploading → converting → ready/error/cancelled |
| progress | Float | 0.0–100.0 |
| filename | String(512) | Имя выходного файла |
| file_size | Integer | Размер результата (байты) |
| error | String(1024) | Текст ошибки |
| original_filename | String(512) | Оригинальное имя файла пользователя |
| original_ext | String(10) | Исходное расширение |
| category | String(20) | video / audio / image / document |
| target_format | String(10) | Целевой формат |
| options | String(4096) | JSON с настройками конвертации |
| hidden | Boolean | Для dismiss/restore (история) |
| created_at, updated_at, completed_at | DateTime(tz) | Временные метки |

### 3.4 Схемы (`app/schemas/convert.py`)

**Константы:**
- `ALLOWED_INPUT_EXTS` — dict {ext: category} (32 расширения)
- `BLOCKED_EXTENSIONS` — 11 запрещённых (.exe, .bat, .cmd, .sh, .ps1, .com, .scr, .msi, .dll, .so, .bin)
- `MAX_FILE_SIZE = 500MB`, `MAX_BATCH_SIZE = 20`

**Модели настроек:**
- `VideoConvertOptions` — resolution, codec, bitrate, fps, audio_codec
- `AudioConvertOptions` — bitrate, sample_rate, channels
- `ImageConvertOptions` — quality (1-100), width, height, keep_aspect

**Request/Response:**
- `ConvertStartRequest` — task_id, target_format, options
- `BatchConvertRequest` — items: list[ConvertStartRequest] (max 20)
- `UploadResponse` — task_id, original_filename, original_ext, category, file_size
- `CapabilitiesResponse` — category, target_formats, settings_fields
- `ConvertTaskStatus` — полный статус задачи с прогрессом
- `ConvertTaskListItem` — облегчённая версия для списков
- `QuotaResponse` — used, limit

### 3.5 Сервис (`app/services/convert_service.py`)

**Архитектура:** In-memory dict `_active_tasks` + `threading.Lock` (паттерн youtube_service.py).
DB persistence только при смене статуса. Eviction из памяти через 30с после терминального статуса.

**Движки конвертации:**

| Движок | Прогресс | Timeout |
|--------|----------|---------|
| `_convert_video` (FFmpeg) | `ffmpeg -progress pipe:1` → `out_time_us` | 30 мин |
| `_convert_audio` (FFmpeg) | `ffmpeg -progress pipe:1` → `out_time_us` | 10 мин |
| `_convert_image` (Pillow) | 0 → 100 мгновенно | 2 мин |
| `_convert_document` (LibreOffice) | 0 → 100 по завершению | 120 с |

**CRUD-хелперы:** get_task_for_user, get_user_tasks, get_hidden_tasks, dismiss_task, restore_task, dismiss_completed_tasks, cancel_task, create_batch_zip.

**Без кэширования** — каждая конвертация выполняется заново, нет video_id/cache_source_task_id.

### 3.6 API роутер (`app/routers/convert.py`)

| Метод | URL | Описание |
|-------|-----|----------|
| POST | `/api/convert/upload` | Загрузить файл(ы), multipart/form-data, до 20 файлов |
| GET | `/api/convert/capabilities/{ext}` | Доступные форматы + настройки для расширения |
| POST | `/api/convert/start` | Начать конвертацию одного файла |
| POST | `/api/convert/batch` | Начать пакетную конвертацию |
| GET | `/api/convert/status/{task_id}` | Прогресс конвертации (in-memory → DB fallback) |
| GET | `/api/convert/file/{task_id}` | Скачать результат (FileResponse) |
| GET | `/api/convert/batch/{batch_id}/zip` | Скачать все файлы batch'а как ZIP |
| GET | `/api/convert/tasks` | Активные (non-hidden) задачи пользователя |
| GET | `/api/convert/tasks/history` | Dismissed задачи в пределах TTL (для истории) |
| DELETE | `/api/convert/task/{task_id}` | Dismiss (hidden=True) |
| DELETE | `/api/convert/tasks/completed` | Dismiss всех терминальных задач |
| POST | `/api/convert/task/{task_id}/restore` | Восстановить из истории |
| DELETE | `/api/convert/cancel/{task_id}` | Отменить конвертацию |
| GET | `/api/convert/quota` | Дневной лимит и использование |

**Защита:** HTTPBearer auth, permission check (`user.permissions.converter`), daily quota (`user.limits.convert_daily`), audit logging.

### 3.7 Безопасность
- UUID имена файлов на диске (входной файл)
- Проверка MIME + расширения
- Блокировка исполняемых файлов (11 расширений)
- Изолированная папка `uploads/{task_id}/`
- Макс 500MB на файл, макс 20 файлов в пакете
- Ownership check на каждом endpoint
- LibreOffice: `--norestore --nolockcheck`
- Pillow: `Image.MAX_IMAGE_PIXELS` guard
- FFmpeg: timeout per category

---

## 🎨 Frontend

### 3.8 Страница (`src/pages/Converter/`)

| Файл | Назначение |
|------|------------|
| `ConverterPage.tsx` | Главный оркестратор: upload queue → active tasks → history |
| `ConverterPage.module.css` | Стили страницы |
| `FileDropZone.tsx` | Drag-and-drop зона с upload progress |
| `FileDropZone.module.css` | Стили drop zone |
| `FileItem.tsx` | Карточка файла: имя, категория, размер, format selector, gear button |
| `FileItem.module.css` | Стили карточки файла |
| `ConvertSettings.tsx` | Панель настроек (зависит от категории): sliders, dropdowns |
| `ConvertSettings.module.css` | Стили панели настроек |
| `ConvertProgress.tsx` | Карточка задачи: progress bar, status badge, action buttons, expiry countdown |
| `ConvertProgress.module.css` | Стили прогресса |
| `types.ts` | TypeScript типы и интерфейсы |
| `converterApi.ts` | API-клиент (axios) |
| `utils.ts` | Утилиты: formatFileSize, CATEGORY_MAP, FORMAT_OPTIONS, triggerBlobDownload |

### 3.9 История конвертаций

Паттерн из YouTube Downloader, но **без кэширования**:
- Завершённые задачи можно dismiss → переходят в collapsible History секцию
- Из истории можно restore обратно в активные
- Файлы доступны для скачивания 6 часов (FILE_TTL_HOURS)
- Countdown до истечения файла ("Осталось Xч Yм")
- Если файл истёк → "Файл удалён", кнопка download disabled

### 3.10 UX-flow
```
1. Drag-and-drop файлы → upload progress (multipart, per-batch progress)
2. Автоопределение категории → показать dropdown целевых форматов
3. (Опционально) ⚙ настроить параметры per file
4. [Конвертировать всё] → polling каждые 2с (pause при hidden tab)
5. [Скачать] individual / [Скачать всё ZIP] для batch
6. Dismiss → History секция (collapsible)
7. Restore / Re-download из History
```

### 3.11 Интеграция
- `App.tsx` — route `/converter` уже настроен с `requiredPermission="converter"`
- `Sidebar.tsx` — `enabled: true` (ранее было false с badge "Скоро")
- `main.py` — router уже подключён (`app.include_router(convert.router)`)
- `ProtectedRoute.tsx` — permission "converter" уже поддерживается
- Cleanup scheduler — `uploads/{task_id}/` очищается существующим scheduler'ом по FILE_TTL_HOURS

---

## ✅ Критерии завершения
- [x] Модель ConvertTask + миграция
- [x] Pydantic-схемы для всех request/response
- [x] Сервис конвертации (4 движка + CRUD + batch ZIP)
- [x] API роутер (14 endpoints)
- [x] Frontend: FileDropZone (drag-and-drop)
- [x] Frontend: FileItem (format selector)
- [x] Frontend: ConvertSettings (per-category settings)
- [x] Frontend: ConvertProgress (progress + history)
- [x] Frontend: ConverterPage (orchestrator)
- [x] История конвертаций (dismiss/restore/download)
- [x] Sidebar enabled
- [x] TypeScript компиляция: 0 ошибок
- [x] Python импорт: все модули резолвятся
- [ ] Pillow добавлен в requirements.txt
- [ ] E2E тестирование всех 4 категорий
- [ ] Мобильная адаптация проверена
