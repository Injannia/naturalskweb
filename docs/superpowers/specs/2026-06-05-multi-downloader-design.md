# Multi downloader — дизайн модуля

**Дата:** 2026-06-05
**Статус:** утверждён, готов к планированию
**Автор:** brainstorming-сессия

## 1. Цель и границы

Новый, 4-й полноправный модуль NaturalskWeb для скачивания видео по ссылке.
Площадки-примеры в UI: **Pinterest, Twitter/X, TikTok (без водяного знака), VK**.
Технически принимается ссылка с любого сайта, поддерживаемого yt-dlp; 4 названные
площадки — основной кейс и примеры в плейсхолдере/описании.

Ввод: **одно поле URL + автодетект площадки** (yt-dlp определяет экстрактор сам),
показ распознанной иконки площадки.

Опции скачивания (простой набор):
- `mp4` — лучшее доступное качество (video+audio merge);
- «только аудио» → `mp3`.

Выбора разрешения нет (большинство целевых площадок отдают один видеопоток).
TikTok без водяного знака — поведение экстрактора yt-dlp по умолчанию, спец-логика
не требуется.

**Тип интеграции:** стандартная модуль-интеграция (permission-тоггл, дневной
лимит/квота, мониторинг usage, плитка HomePage, UsageBars в профиле, nav-пункт) —
как `youtube`/`converter`/`image`. Без кросс-модульного пайплайна и без общей
истории/кэша с YouTube.

## 2. Архитектура бэкенда (подход A)

Новый модуль со своей таблицей задач, переиспользующий готовую инфраструктуру
хранения/раздачи/очистки. Существующий YouTube-модуль **не модифицируется**
(нулевой риск регресса).

### 2.1 Модель `app/models/multi_download_task.py`

Таблица `multi_download_tasks` (по образцу `ConvertTask` — отдельная таблица на
модуль, чтобы задачи Multi downloader не попадали в списки YouTube):

| Поле | Тип | Назначение |
|------|-----|-----------|
| `id` | String(36) PK | UUID задачи |
| `user_id` | Integer FK users.id, index | владелец |
| `status` | String(20) | pending/downloading/converting/ready/error/cancelled |
| `progress` | Float | 0..100 |
| `filename` | String(512) nullable | итоговое имя файла |
| `file_size` | Integer nullable | байты |
| `error` | String(1024) nullable | сообщение об ошибке |
| `url` | String(2048) | исходная ссылка |
| `title` | String(512) nullable | заголовок видео |
| `thumbnail` | String(2048) nullable | URL превью-постера (remote) |
| `platform` | String(40) nullable | распознанная площадка (extractor key) |
| `audio_only` | Boolean default False | mp3-режим |
| `shared_file_id` | String(36) nullable | ссылка на SharedFile с файлом |
| `hidden` | Boolean default False, server_default "0" | soft-delete для списков |
| `created_at` | DateTime(tz) server_default now | |
| `updated_at` | DateTime(tz) onupdate | |
| `completed_at` | DateTime(tz) nullable | |

### 2.2 Сервис `app/services/multidl_service.py`

Тонкий, без playlist / лестницы качества / cache-hit / dedup.

- `get_info(url)` → `{title, thumbnail, duration, platform}`.
  yt-dlp `extract_info(download=False)`, `noplaylist=True`, выполняется в треде
  через `asyncio.to_thread` с таймаутом (30 с). Отдаёт метаданные для превью.
- `download(url, audio_only, task_id, shared_file_id)` — фоновая корутина:
  - `mp4`: format selector best video+audio, `merge_output_format="mp4"`;
  - audio: `bestaudio/best` → ffmpeg → `mp3` (`libmp3lame`), удаление промежуточного.
  - In-memory progress-реестр + `threading.Lock` (паттерн из `youtube_service`):
    hot-path прогресс в памяти, персист в БД на переходах статуса
    (pending → downloading → converting → ready/error/cancelled).
  - Поддержка отмены: проверка cancelled-флага в progress-hook + реестр активных
    `yt_dlp.YoutubeDL` для прерывания.
- `create_task`, `get_task_for_user`, `get_download_progress`, `get_user_tasks`,
  `cancel_task`, `dismiss_task` + retry-хелпер — по аналогии с youtube, но
  упрощённые (без cache/dedup-веток; `/restore` не экспонируется).

**Переиспользование `SharedFile`** для хранения/раздачи/TTL: завершённая задача
создаёт запись `SharedFile` с файлом в `uploads/{shared_file_id}/`. Поле
`video_id` ставится `f"multidl:{uuid}"` — гарантирует отсутствие коллизии с
YouTube-кэшем (`youtube_service.find_cached_shared_file` фильтрует по
`video_id`+`format`+`quality`; multidl-значения никогда не совпадут с 11-символьными
YouTube-ID). Существующий `cleanup_expired_shared_files` (APScheduler, каждые 30 мин)
сам удалит `uploads/{id}` и запись по истечении `FILE_TTL_HOURS`.

### 2.3 Util `app/utils/ffmpeg.py`

Вынос `find_ffmpeg()` (поиск пути к ffmpeg) в общий util для использования из
`multidl_service`. YouTube-сервис не трогаем (он сохраняет свою локальную копию,
миграция youtube на общий util — вне scope).

### 2.4 Роутер `app/routers/multidl.py`, prefix `/api/multidl`

```
POST   /info            — превью: {title, thumbnail, platform, duration}
POST   /download        — старт загрузки (202 Accepted), body: {url, audio_only}
GET    /status/{id}     — прогресс задачи
GET    /file/{id}       — отдать готовый файл (authed, FileResponse)
DELETE /cancel/{id}     — отмена активной задачи
GET    /tasks           — список задач юзера (карточки + история), hidden=False
POST   /retry/{id}      — повтор failed/cancelled задачи
DELETE /task/{id}       — dismiss (hidden=True)
GET    /quota           — {used, limit} за сегодня
```

Guards-хелперы в роутере (зеркало youtube): `_require_multidl_permission` (403),
`_get_quota`, `_check_daily_limit` (429), `_increment_usage`. Регистрация в
`main.py`: `app.include_router(multidl.router)`.

Схемы — `app/schemas/multidl.py`: `InfoRequest/InfoResponse`, `DownloadRequest`
(`url`, `audio_only`), `DownloadStatus`, `QuotaResponse`.

### 2.5 Миграция

Новая ревизия Alembic **только** для таблицы `multi_download_tasks`
(`cd backend && .venv/bin/alembic revision --autogenerate -m "add multi_download_tasks"`).
Схема `users` (JSON-колонки) не меняется.

## 3. Точки стандартной интеграции

Ключи: permission **`multidl`**, limit **`multidl_daily`** (дефолт 50),
usage **`multidl`**.

Места правок:
- `models/user.py` — дефолты `permissions`, `limits`, `usage_today` (+`multidl`).
- `routers/admin/users.py` — create-дефолты `permissions`/`limits`.
- `main.py` — `_create_superadmin` (permissions/usage_today), `reset_daily_usage`.
- **`_increment_usage` во всех 4 роутерах** (`youtube`, `convert`, `image`,
  `multidl`): при смене даты каждый перезаписывает `usage_today` свежим dict — все
  они сейчас содержат 3 ключа и затёрли бы `multidl`. Добавить `"multidl": 0` во
  все четыре reset-dict, иначе межмодульный usage обнуляется.
- `routers/admin/monitoring.py` — usage-счётчики (добавить ключ `multidl`).
- `cleanup_stale_pending_tasks` в `main.py` — добавить скан `multi_download_tasks`
  (отмена/чистка зависших pending, как для остальных task-таблиц).

**Доступ существующих пользователей:** ключа `multidl` нет в их `permissions` →
`.get("multidl", False)` → доступа нет, пока админ не включит тоггл. Новые
пользователи получают `multidl: True` по умолчанию. Backfill-миграция прав
существующим юзерам **не делается** (по умолчанию выкл; включается админом точечно).

## 4. Frontend

Каталог `pages/MultiDownloader/`: `MultiDownloaderPage.tsx`, `multidlApi.ts`,
`DownloadCard.tsx`, `*.module.css`. Дизайн-язык Indigo Nebula, UI-kit
(`Button`/`Card`/`Input`/`DropZone` где уместно), токены из `variables.css`.

Поток UX:
1. Одно поле URL (плейсхолдер с примерами: Pinterest / Twitter·X / TikTok / VK) →
   запрос `/info` → карточка с превью-постером (remote `thumbnail`), заголовком,
   иконкой распознанной площадки.
2. Переключатель «mp4 / только mp3» → кнопка «Скачать» → `/download`.
3. Поллинг `/status/{id}` (как youtube), карточка показывает прогресс/скорость.

**Карточки/история — как в YouTube**, плюс **превью скачанного — как в Image**:
после статуса `ready` карточка показывает inline authed-плеер скачанного файла —
`<video>` для mp4, `<audio>` для mp3 — через blob, загружаемый api-клиентом с
авторизацией. Обобщить существующий `useAuthedImage` в `useAuthedMedia` (blob +
`URL.createObjectURL` + ревок на размонтировании), либо добавить параллельный хук;
переиспользовать паттерн `AvatarImage`/`ImageCompare`.

Точки интеграции фронта:
- `App.tsx` — роут `/multidl` + `<ProtectedRoute requiredPermission="multidl">`.
- `ProtectedRoute.tsx` — расширить тип `requiredPermission` ключом `'multidl'`.
- `HomePage.tsx` — плитка модуля (иконка lucide, напр. `Download`); счётчик
  «N из 4 модулей» (сейчас захардкожено 3 — обновить на 4 и список пермишенов).
- `Sidebar` + `BottomNav` — nav-пункт с фильтрацией по `permissions.multidl`.
- `CreateUserModal.tsx` + `EditUserModal.tsx` — чекбокс пермишена (массив ключей
  `[..., 'multidl']`).
- `UsageBars.tsx` — строка модуля (`key: 'multidl'`, `limitKey: 'multidl_daily'`).

## 5. Обработка ошибок

Зеркало youtube-роутера, тексты на русском:
- 403 — нет доступа к модулю;
- 429 — достигнут дневной лимит;
- 408 — таймаут yt-dlp при получении info;
- 404 — видео недоступно (приватное/удалено/гео-блок);
- 400 — невалидный/неподдерживаемый URL;
- 500 — прочие ошибки (лог + generic-сообщение).

## 6. Тестирование (backend)

`tests/test_multidl.py`, direct-call паттерн (вызов функций роутера напрямую,
`_make_request()`, `db_session`-фикстура):
- permission-gate → 403 без пермишена;
- quota → 429 при исчерпании + проверка инкремента `usage_today["multidl"]`;
- create → status → cancel → retry жизненный цикл;
- dismiss (`hidden=True`) исключает из `/tasks`;
- `get_info` с мок-yt-dlp (title/thumbnail/platform);
- регресс: multidl-SharedFile (`video_id="multidl:..."`) не матчится
  `youtube_service.find_cached_shared_file`.

Фронт: при необходимости — unit-тест `DownloadCard` (Vitest), по образцу
`ImageProgress.test.tsx`.

## 7. Объём работ

- 1 модель + Alembic-миграция;
- 1 сервис (`multidl_service.py`);
- 1 роутер (`multidl.py`) + схемы;
- 1 util (`ffmpeg.py`);
- ~6 точек бэк-интеграции (permission/limit/usage/monitoring/cleanup);
- новая frontend-страница (`MultiDownloader/`) + `useAuthedMedia`;
- ~7 точек фронт-интеграции;
- backend-тесты + опц. frontend-тест.

YouTube-модуль не модифицируется. Существующая инфраструктура хранения/TTL/cleanup
переиспользуется через `SharedFile`.
