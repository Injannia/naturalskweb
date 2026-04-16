# YouTube Downloader: Shared File Cache Redesign

**Date:** 2026-04-16  
**Status:** Approved

## Problem

Текущая реализация кэша привязывает скачанный файл к первому пользователю, который его загрузил. Если этот пользователь выполняет permanent delete, зависимые таски других пользователей теряют ссылку на файл (`cache_source_task_id` зануляется), хотя файл физически остаётся на диске — ссылки рвутся.

## Goal

Файл не принадлежит ни одному пользователю. Запись `download_tasks` — это пользовательский «взгляд» на файл. Permanent delete удаляет только эту запись. Файл живёт по TTL (6 часов), независимо от действий пользователей.

---

## Data Model

### Новая таблица `shared_files`

| Поле | Тип | Описание |
|------|-----|---------|
| `id` | UUID (PK) | Идентификатор файла |
| `video_id` | str(64), indexed | Cache-ключ: YouTube ID (11 символов) или SHA-1 хэш плейлиста |
| `format` | str | mp4 / mp3 / wav |
| `quality` | str | best / 1080p / 720p / 480p / 360p |
| `filename` | str | Имя файла для скачивания |
| `file_size` | int? | Размер в байтах |
| `expires_at` | datetime | `completed_at + FILE_TTL_HOURS` |
| `created_at` | datetime | |

Файлы хранятся в `uploads/{shared_file_id}/`.

### Изменения в `download_tasks`

- **Удалить:** `cache_source_task_id`
- **Добавить:** `shared_file_id` (FK → `shared_files.id`, nullable — NULL пока идёт загрузка)

---

## Cache Flow

### Новый запрос на скачивание

1. Генерируем `video_id` (cache-ключ) как сейчас — через `extract_video_id()` или `compute_playlist_cache_key()`
2. Ищем в `shared_files` по `(video_id, format, quality)` где `expires_at > now + 5min` и файл существует на диске
3. **Cache hit:** создаём таск со статусом `ready`, `shared_file_id = {найденный id}` — загрузка не запускается
4. **Cache miss:** создаём таск со статусом `pending`, `shared_file_id = NULL`, запускаем загрузку

### Завершение загрузки

1. Создаём запись `shared_files` (файл уже в `uploads/{shared_file_id}/`)
2. Обновляем `task.shared_file_id`
3. Статус таска → `ready`

### Параллельные загрузки одного видео

Если два пользователя запросили одно видео одновременно (cache miss у обоих):
- Оба запускают загрузку независимо
- Первый завершивший создаёт `shared_file`
- Второй при завершении проверяет: если `shared_file` уже существует — ссылается на него, свою директорию удаляет

### Раздача файла

`resolve_file_task_id()` заменяется на `resolve_shared_file_path()`:
- Берём `task.shared_file_id`
- Возвращаем путь из `shared_files.file_path`
- Никакой индирекции через другой таск

---

## Delete & Cleanup

### Soft delete (скрыть из списка)

Поведение не меняется: `task.hidden = True`.

### Permanent delete

- Удаляем только запись `download_tasks`
- `shared_files` и файл на диске не трогаем
- Никаких проверок зависимостей не нужно

### TTL-очистка (APScheduler — активная)

Добавляем периодическую задачу (каждый час):

1. Находим все `shared_files` где `expires_at < now`
2. Удаляем директорию `uploads/{shared_file_id}/` с диска
3. Удаляем запись из `shared_files`
4. Удаляем связанные `download_tasks` (каскадно или вручную)

Таски без `shared_file_id` (статус `pending/downloading/error/cancelled`) очищаются отдельно по `created_at + FILE_TTL_HOURS`.

---

## Migration

Alembic-миграция без перемещения файлов на диске:

1. **Создать таблицу `shared_files`**
2. **Для существующих исходных тасков** (status=`ready`, `cache_source_task_id=NULL`):
   - Создать запись `shared_files` с `file_path = uploads/{task_id}/`
   - Присвоить `task.shared_file_id`
3. **Для существующих кэш-хит тасков** (`cache_source_task_id` не NULL):
   - Найти `shared_file` источника
   - Присвоить `task.shared_file_id`
4. **Удалить колонку `cache_source_task_id`** из `download_tasks`
5. **Добавить FK `shared_file_id`** в `download_tasks`

Файлы на диске не переименовываются. Откат (downgrade) восстанавливает старую схему.

---

## Affected Files

### Backend
- `backend/app/models/download_task.py` — убрать `cache_source_task_id`, добавить `shared_file_id` FK
- `backend/app/models/shared_file.py` — новая модель
- `backend/app/models/__init__.py` — экспорт новой модели
- `backend/app/services/youtube_service.py` — переработать `find_cached_task`, `create_cached_task`, `delete_task_permanent`, `resolve_file_task_id`; добавить TTL-очистку
- `backend/app/routers/youtube.py` — убрать логику постоянного удаления файлов
- `backend/app/schemas/youtube.py` — обновить схемы ответов
- `backend/alembic/versions/` — новая миграция

### Frontend
- `frontend/src/pages/YouTube/types.ts` — убрать `cacheSourceTaskId`, добавить `sharedFileId` (опционально, если нужно)
- `frontend/src/pages/YouTube/YouTubePage.tsx` — без изменений в логике UI
