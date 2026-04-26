# Phase 5 — Admin Panel, Monitoring, Личный кабинет, Главная страница

> Дата: 2026-04-26
> Источник требований: `spec/phase-5-admin-monitoring.md` + дополнения от пользователя
> Статус: design (на ревью)

## Обзор

Фаза 5 расширяет NaturalskWeb тремя крупными блоками:

1. **Главная страница** (`/`) — новая стартовая точка после логина: логотип + плитки перехода в модули и в личный кабинет/админку.
2. **Личный кабинет** (`/me`) — для всех пользователей: профиль, аватар, лимиты использования, активные сессии, смена пароля.
3. **Admin Panel** (`/admin`) — полнофункциональная админка с табами: Пользователи, Аудит-лог, Мониторинг (только superadmin), Мой профиль.

Дополнительные сквозные изменения: загрузка аватара (Pillow + WebP), polling `/auth/me` для мгновенной реакции на смену прав, расширение `User` (avatar_path, avatar_version, is_deleted, kicked_at).

БД пересоздаётся (Alembic-миграции на этой стадии не используются).

---

## 1. Маршрутизация и навигация

### 1.1 Маршруты frontend

```
/                — HomePage (новая, защищённая, для всех залогиненных)
/me              — ProfilePage (новая, защищённая, для всех)
/admin           — AdminPage (защищённая, role ∈ {admin, superadmin})
/youtube         — без изменений
/converter       — без изменений
/image           — без изменений
/login           — без изменений
/change-password — без изменений
*                — Navigate to "/"  (раньше → /youtube)
```

После логина и после смены пароля — редирект на `/` (а не `/youtube`).

### 1.2 Sidebar

Перестраивается под роль. Все видят пункт «Главная» (Home icon → `/`).
Дальше — модули по permissions. Внизу, после разделителя:

- `user`: «Личный кабинет» (User icon → `/me`).
- `admin` / `superadmin`: «Admin Panel» (Shield icon → `/admin`). Личного кабинета как отдельного пункта в sidebar нет — он живёт внутри Admin Panel вкладкой «Мой профиль».

### 1.3 ProtectedRoute

Существующая логика сохраняется. Добавляется проверка роли для отдельных табов внутри Admin Panel (Мониторинг — только superadmin, на уровне UI и на уровне эндпоинтов).

---

## 2. Главная страница

### 2.1 Файлы

- `frontend/src/pages/Home/HomePage.tsx`
- `frontend/src/pages/Home/Home.module.css`

### 2.2 Layout

В `MainLayout` (Sidebar + Topbar + StarryBackground):

- В центре `main`-области, вертикально по центру:
  - **Логотип**: текст «Naturalsk**Web**» крупным размером (`fs-3xl` или больше), монопространственный шрифт, акцентная часть «Web» в `var(--accent)`. Под ним короткая надпись-подзаголовок (финальный текст подбирается при реализации, например «Закрытая рабочая среда»).
  - **Сетка плиток** под логотипом: до 4 плиток в ряд на десктопе, 1 в столбец на мобиле (≤ 768px).

### 2.3 Плитки

Каждая плитка — `<NavLink>`-карточка с иконкой Lucide, названием и короткой подписью. Появление зависит от прав:

| Плитка | Условие | Маршрут |
|--------|---------|---------|
| YouTube Downloader | `permissions.youtube` | `/youtube` |
| File Converter | `permissions.converter` | `/converter` |
| Image Processor | `permissions.image` | `/image` |
| Личный кабинет | `role === 'user'` | `/me` |
| Admin Panel | `role ∈ {'admin','superadmin'}` | `/admin` |

Плитка «Личный кабинет» / «Admin Panel» отображается всегда для соответствующей роли.

**Пустое состояние:** если у `user` отключены все три модуля — на главной остаётся только плитка «Личный кабинет», что закрывает кейс пустой главной.

### 2.4 Стиль плиток

Карточка с тёмным фоном, лёгкой `border`, hover — свечение `accent-glow` и `translateY(-2px)`. Иконка ~36–48px, название `fs-base`, описание `fs-sm` `text-muted`. Используются существующие CSS-переменные проекта.

---

## 3. Личный кабинет (ProfileTab)

Один React-компонент `ProfileTab.tsx` используется и на странице `/me`, и как таб в `/admin`.

### 3.1 Файлы

- `frontend/src/pages/Profile/ProfilePage.tsx` — обёртка для `/me` (хедер «Личный кабинет» + `<ProfileTab />`).
- `frontend/src/pages/Profile/ProfileTab.tsx` — основной контент.
- Подкомпоненты:
  - `frontend/src/pages/Profile/AvatarUploader.tsx`
  - `frontend/src/pages/Profile/UsageBars.tsx`
  - `frontend/src/pages/Profile/SessionsList.tsx`
  - `frontend/src/pages/Profile/ChangePasswordForm.tsx`
  - `frontend/src/pages/Profile/ChangeUsernameForm.tsx`
- `frontend/src/pages/Profile/Profile.module.css`

### 3.2 Содержимое (порядок секций сверху вниз)

1. **Шапка профиля** — крупный аватар (128px) слева, справа: username (с inline edit-кнопкой), роль (read-only, monospace), дата создания, последний вход (дата + IP + сокращённый user-agent).
2. **Лимиты использования** — три строки прогресс-баров (YouTube / Converter / Image). Формат: `YouTube · 12 / 50` + горизонтальный bar.
   - < 70%: зелёный (`accent`)
   - 70–90%: жёлтый (`warning`)
   - > 90%: красный (`danger`)
   - Под бар-блоком: «Лимиты обнулятся через 14 ч 22 мин» (расчёт на клиенте от `usage_reset_date` + 24ч UTC).
3. **Активные сессии** — список карточек: IP, user-agent (короткое имя браузера через парсер), создана/истекает, кнопка «Завершить» (DELETE сессии). Сверху — кнопка «Завершить все, кроме текущей». Текущая сессия отмечена бейджем «Эта сессия».
4. **Безопасность** — кнопка «Сменить пароль» открывает модалку с формой `current/new/confirm`.

### 3.3 Эндпоинты для пользователя (новый router `routers/me.py`)

```
GET    /api/me                       — расширенный профиль (UserMeResponse)
PATCH  /api/me                       — { username }, валидация уникальности
POST   /api/me/avatar                — multipart upload
DELETE /api/me/avatar                — удалить аватар
GET    /api/me/sessions              — список своих active_sessions
DELETE /api/me/sessions/{id}         — завершить свою сессию
DELETE /api/me/sessions              — завершить все, кроме текущей
```

`POST /api/auth/change-password` уже существует — его не дублируем.

`GET /api/me` возвращает то же, что `GET /api/auth/me`, но с расширенными полями (см. `UserMeResponse` в §6.6).

### 3.4 Edge case

Если между логином и открытием страницы пользователь оказался удалённым/деактивированным — polling `/auth/me` (см. §7.1) сделает logout с уведомлением.

---

## 4. Admin Panel

### 4.1 Файлы

- `frontend/src/pages/Admin/AdminPage.tsx` — layout с табами (заменяет нынешний Placeholder).
- `frontend/src/pages/Admin/UsersTab.tsx`
- `frontend/src/pages/Admin/AuditLogTab.tsx`
- `frontend/src/pages/Admin/MonitoringTab.tsx`
- Модалки: `CreateUserModal.tsx`, `EditUserModal.tsx`, `ResetPasswordModal.tsx`, `ConfirmDeleteModal.tsx`
- `frontend/src/pages/Admin/Admin.module.css`

### 4.2 Табы (видимость по роли)

| Таб | admin | superadmin |
|-----|-------|-----------|
| Пользователи | ✓ | ✓ |
| Аудит-лог | ✓ | ✓ |
| Мониторинг | ✗ | ✓ |
| Мой профиль | ✓ (`<ProfileTab />`) | ✓ |

Активный таб хранится в URL как query-param: `/admin?tab=users` (default), `audit`, `monitoring`, `profile`. Это даёт shareable ссылки и сохранение состояния при F5.

### 4.3 UsersTab

**Колонки таблицы:** аватар (24px), username, роль (badge), статус (active / inactive / deleted), создан, последний вход, использование сегодня (компактно: `Y 12/50 · C 4/100 · I 0/50`).

**Над таблицей:**
- Поиск по username (debounced).
- Фильтр по роли (все / user / admin / superadmin).
- Фильтр по статусу (active / inactive / deleted — последний только для superadmin).
- Кнопка «➕ Создать пользователя».

**Пагинация:** offset/limit, шаг 20. Кнопки «Назад / Вперёд» + индикатор `1-20 из 47`.

**Действия в строке** (видимость зависит от ролевых правил §7.3):
- 👁 «Подробно» — read-only вариант `EditUserModal`. Появляется в случаях, когда полный редактор недоступен (admin смотрит на superadmin, или пользователь смотрит на самого себя).
- ✏️ «Редактировать» (PATCH user).
- 🔑 «Сбросить пароль» (показывает новый пароль один раз).
- ⏻ «Включить/Выключить» (toggle-active).
- 🗑 «Удалить» (soft delete, только superadmin, не для себя).

### 4.4 AuditLogTab

**Таблица:** дата, пользователь (username + ссылка для фильтра), действие (badge с цветом по типу), детали (JSON в раскрывающемся блоке), IP.

**Фильтры сверху:**
- Поиск по username (заполняет `?user_id=`).
- Селект action (login / logout / login_failed / change_password / user_created / ... — фиксированный список из enum'а actions).
- Диапазон дат (date inputs `from`–`to`).
- Кнопка «Экспорт CSV» — скачивает `/api/admin/audit-log/export.csv` с теми же фильтрами.

**Пагинация:** offset/limit=50, кнопки навигации. Бесконечный скролл не используется.

### 4.5 MonitoringTab (только superadmin)

**Карточки в верхнем ряду:** CPU%, RAM (used/total + bar), Disk (used/total + bar), Uptime (`12д 4ч 22м`).

**Второй ряд:** счётчики операций сегодня (Downloads / Conversions / Image ops), Storage used (МБ), Active sessions.

**Третий ряд:** Top-5 пользователей за сегодня (имя + сумма операций + bars).

**Подвал:** строка версий — `Python 3.12.3 · ffmpeg 6.1.1 · yt-dlp 2024.05.02`.

**Обновление:** `setInterval(30000)` — одновременный запрос `/system` + `/stats`. Останавливается при `document.visibilityState === 'hidden'`, возобновляется при возврате на вкладку. При размонтировании — `clearInterval`.

### 4.6 Tab «Мой профиль»

Просто `<ProfileTab />` без обёртки. Тот же компонент и данные, что на `/me`.

---

## 5. Аватары

### 5.1 Хранение

- Файлы: `backend/data/avatars/{user_id}.webp`. Папка создаётся при старте, путь добавляется в `Settings.AVATARS_DIR`.
- Форматы на вход: `image/jpeg`, `image/png`, `image/webp`. Лимит 5 МБ.
- Обработка через Pillow: `Image.open(...).convert("RGB").thumbnail((256, 256))` после клиентского кропа квадрата → перезапись в WebP, quality 88. Финальный файл ~10–30 КБ.
- Поле в `users`: `avatar_path: str | None` хранит относительный путь (`avatars/{user_id}.webp`) или `None`. Используется только как флаг существования и для `os.remove` при удалении.

### 5.2 Эндпоинты

```
POST   /api/me/avatar               — multipart 'file', возвращает {avatar_path, avatar_version}
DELETE /api/me/avatar               — удаляет файл, обнуляет avatar_path
GET    /api/users/{id}/avatar       — отдаёт WebP залогиненному (FileResponse), 404 если нет
```

**Cache-busting:** при апдейте инкрементится `users.avatar_version: int`. Фронт ходит за `/api/users/{id}/avatar?v={avatar_version}`. Без этого браузер закэширует старую картинку. На бэке параметр `v` не используется — он только меняет URL.

`GET /api/users/{id}/avatar` доступен любому залогиненному (закрытая команда — норм). Защищён обычным `Depends(get_current_user)`. Для не-найденного аватара — 404, фронт показывает fallback.

### 5.3 Frontend

**`AvatarUploader.tsx`** (используется в ProfileTab):

- Большой круглый аватар (128×128).
- Если есть аватар — `<img src="..." />` через хук `useAuthedImage`.
- Если нет — иконка `User` из lucide-react, размер ~64px, `text-secondary`, на круглом фоне `bg-card`.
- Кнопки под аватаром: «Загрузить» (открывает file-picker) и «Удалить» (если аватар есть).
- После выбора файла — модалка с canvas-кропом: показываем выбранное изображение, круглую/квадратную область выбора, ползунок зума, drag для смещения. Кнопки «Сохранить» / «Отмена». Используется библиотека **react-easy-crop**.
- При сохранении: canvas → blob (JPEG quality 92) → `POST /api/me/avatar` (FormData). После 200 — обновляется `auth.user.avatar_version`, чтобы все `<img>` перезагрузились.

**`useAuthedImage(url)` hook** — общий helper для авторизованной загрузки картинок:
- Через axios скачивает blob с Bearer-токеном.
- Возвращает `URL.createObjectURL(blob)`.
- На размонтировании — `URL.revokeObjectURL(...)`.

**`AvatarImage.tsx`** — общий маленький компонент для отображения аватара по `userId`/`avatar_version`. Используется в ProfileTab, Topbar, UsersTab. Внутри `useAuthedImage`. При отсутствии или ошибке — fallback на иконку User.

### 5.4 Зависимости

- Pillow уже есть (используется в `image_service`).
- `react-easy-crop` добавляется в `frontend/package.json`.

---

## 6. Backend: эндпоинты, схемы, БД

### 6.1 Изменения модели `User`

Добавляются поля в `backend/app/models/user.py`:

```python
avatar_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
avatar_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
kicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

`kicked_at` используется в `get_current_user`: если `payload.iat < user.kicked_at` → 401. Так обнуляются все старые токены при kill-session.

### 6.2 Учёт `is_deleted`

- В `auth.login`: если `user.is_deleted` → возвращаем тот же 401 «Неверный логин или пароль» (не палим факт удаления).
- В `get_current_user`: `if user.is_deleted: raise 401`.
- В `GET /api/admin/users`: по умолчанию `WHERE is_deleted = false`. Параметр `?include_deleted=true` доступен только superadmin.

### 6.3 Применение изменений схемы БД

Миграции Alembic в этой фазе не создаются — БД пересоздаётся:

1. Остановить backend.
2. Удалить `backend/data/naturalsk.db`, `backend/data/naturalsk.db-shm`, `backend/data/naturalsk.db-wal`.
3. Удалить `backend/data/initial_admin_password.txt` (старый пароль admin).
4. Запустить backend — `create_tables()` создаст схему, `_create_superadmin` создаст admin и запишет пароль в `initial_admin_password.txt`.

В плане реализации этот шаг выполняется один раз перед прогоном e2e-тестов.

### 6.4 Карта новых эндпоинтов фазы 5

**Личный кабинет (`routers/me.py`, новый):**

```
GET    /api/me                       — расширенный профиль
PATCH  /api/me                       — { username }
POST   /api/me/avatar                — upload
DELETE /api/me/avatar                — remove
GET    /api/me/sessions              — свои сессии
DELETE /api/me/sessions/{id}         — завершить свою сессию
DELETE /api/me/sessions              — завершить все, кроме текущей
```

**Раздача аватаров (новый `routers/users.py`):**

```
GET    /api/users/{id}/avatar        — WebP, любой залогиненный
```

Эндпоинт оформляется как отдельный роутер с зависимостью `Depends(get_current_user)`. Не лежит в `me.py`, потому что обращается к чужим аватаркам. Не лежит в `admin.py`, потому что доступен любому залогиненному.

**Админка (расширение `routers/admin.py`):**

```
GET    /api/admin/users              — пагинация ?offset&limit&search&role&status&include_deleted
GET    /api/admin/users/{id}         — детали (расширенный объект)
PATCH  /api/admin/users/{id}         — роль, permissions, limits, is_active
DELETE /api/admin/users/{id}         — soft delete (superadmin)
POST   /api/admin/users/{id}/reset-password — генерит пароль, must_change=true
POST   /api/admin/users/{id}/toggle-active   — переименование текущего toggle

GET    /api/admin/audit-log          — фильтры ?user_id&action&from&to&offset&limit
GET    /api/admin/audit-log/export.csv — те же фильтры

GET    /api/admin/sessions           — все активные refresh-сессии
DELETE /api/admin/sessions/{id}      — kill (выставляет users.kicked_at = now)

GET    /api/admin/stats              — расширенная статистика
GET    /api/admin/system             — psutil + версии (только superadmin)
GET    /api/admin/storage            — размер data/, uploads/, файлов
```

### 6.5 Расширение `/api/admin/stats`

```python
class TopUser(BaseModel):
    user_id: int
    username: str
    avatar_version: int
    total_today: int

class AdminStats(BaseModel):
    total_users: int
    active_users: int
    deleted_users: int
    total_downloads_today: int        # sum(usage_today.youtube) по всем users
    total_conversions_today: int      # sum(usage_today.converter)
    total_image_ops_today: int        # sum(usage_today.image)
    storage_used_mb: float            # размер data/ + uploads/
    active_sessions: int              # COUNT active_sessions WHERE expires_at > now
    top_users: list[TopUser]          # 5 пользователей по сумме usage_today
    total_audit_logs: int
```

`storage_used_mb` считается через `os.walk`. Для маленькой команды это быстро; если станет проблемой — добавим in-memory cache на 5 минут.

### 6.6 Pydantic-схемы (новые)

**`schemas/admin.py` (новый):**
- `UpdateUserRequest` (role / permissions / limits / is_active — все опциональные).
- `UserDetailResponse` (полный объект с created_at, last_login, audit-stat и т.п.).
- `UserListItem` (расширение существующего: + avatar_version, is_deleted, role, created_at).
- `SessionItem` (id, user_id, username, ip_address, user_agent, created_at, expires_at).
- `AuditLogFilter` (query-params, валидация дат).
- `SystemInfo` (cpu_percent, ram_used_mb, ram_total_mb, disk_used_gb, disk_total_gb, uptime_seconds, python_version, ffmpeg_version, yt_dlp_version).
- `StorageInfo` (data_size_mb, uploads_size_mb, avatars_size_mb, total_files).
- `TopUser`, `AdminStats` (см. §6.5).

**`schemas/me.py` (новый):**
- `UserMeResponse` — расширение `UserResponse` с `avatar_version`, `created_at`, `last_login`, `usage_reset_date`.
- `UpdateMeRequest` — `{ username: str }`.
- `MySessionItem` — `{ id, ip_address, user_agent, created_at, expires_at, is_current: bool }`.
- `AvatarUploadResponse` — `{ avatar_path: str, avatar_version: int }`.

### 6.7 Зависимости и helper'ы backend

- `require_superadmin` — новый Depends в `dependencies.py` (для `/api/admin/system`, `?include_deleted=true`, DELETE user).
- `psutil` добавляется в `backend/requirements.txt`.
- Helper `_log_audit` существует в `auth.py` — выносится в `app/utils/audit.py` и переиспользуется во всех routers.
- Helper `_get_tool_versions()` — выполняет subprocess `python --version`, `ffmpeg -version`, `yt-dlp --version`, кэширует результат на 1 час in-memory.
- Helper `parse_user_agent(ua: str)` — простой парсер до короткого имени браузера/ОС («Chrome 120 · Linux»). Без отдельной зависимости (regex).

### 6.8 Аудит-лог: новые actions

Константы actions в новом модуле `app/utils/audit_actions.py`:

- `user_created`
- `user_updated`
- `user_deleted`
- `user_password_reset`
- `user_toggled_active`
- `session_killed_by_admin`
- `username_changed`
- `avatar_updated`
- `avatar_removed`

Каждое логируется в соответствующих эндпоинтах с `details` (см. §7.4).

---

## 7. Безопасность, polling, ролевые правила

### 7.1 Polling `/auth/me` на фронте

В `useAuthProvider` добавляется фоновый интервал:

```ts
useEffect(() => {
  if (!user) return
  const id = setInterval(async () => {
    if (document.visibilityState !== 'visible') return
    try {
      const { data } = await api.get<User>('/auth/me')
      setUser(data)  // тригерит ре-рендер ProtectedRoute и др.
    } catch {
      // 401 → axios interceptor рефрешит или вылогинивает
    }
  }, 15_000)
  return () => clearInterval(id)
}, [user?.id])
```

`ProtectedRoute` уже проверяет `permissions` и `role` при каждом рендере → если permission отозвали, происходит `Navigate` в `/`. Если роль понизили с admin до user, находясь на `/admin` → редирект в `/`.

### 7.2 Принудительный logout

Случаи, когда сервер отзывает доступ:

- `is_deleted = true` → 401 на следующем запросе → axios interceptor очистит токены и редирект на `/login`.
- `is_active = false` → то же самое.
- `kicked_at > token.iat` → то же самое (через `get_current_user`).

Toast-уведомление перед редиректом: «Сессия завершена». Чтобы пользователь не думал, что приложение сломалось.

### 7.3 Ролевые проверки на бэке

В `routers/admin.py` появляется helper `can_modify_user(actor, target)`:

**Конкретные правила для PATCH `/api/admin/users/{id}` (admin):**
- ❌ Цель — superadmin.
- ❌ Цель — сам admin (свою роль/permissions/limits через админку не меняет).
- ❌ Изменение поля `role` на `admin` или `superadmin` (admin может только понижать или оставлять `user`).
- ✅ Всё остальное.

**DELETE `/api/admin/users/{id}` (только superadmin):**
- ❌ `id == current_user.id` (защита от самоудаления).

**POST `/api/admin/users` (create):**
- admin: только `role=user`.
- superadmin: любая роль, включая superadmin (несколько superadmin'ов допустимы).

**POST `/api/admin/users/{id}/reset-password`:**
- admin: цель — не superadmin, не себя.
- superadmin: любого, включая себя (кейс — потерял доступ к своему паролю через CLI).

**POST `/api/admin/users/{id}/toggle-active`:**
- admin: цель — не superadmin, не себя.
- superadmin: любого, кроме себя.

### 7.4 Audit-log: формат `details`

- `user_created`: `{target_user_id, target_username, role, permissions, limits}`.
- `user_updated`: `{target_user_id, target_username, changes: {field: [old, new], ...}}`.
- `user_deleted`: `{target_user_id, target_username}`.
- `user_password_reset`: `{target_user_id, target_username}` (без самого пароля).
- `user_toggled_active`: `{target_user_id, target_username, new_state: bool}`.
- `session_killed_by_admin`: `{target_user_id, target_username, session_id}`.
- `username_changed`: `{old_username, new_username}` (action самого пользователя).
- `avatar_updated`, `avatar_removed`: `{}` (action самого пользователя).

### 7.5 Rate limiting

`RateLimitMiddleware` уже есть, новые эндпоинты автоматически попадают под общий лимит 60 req/min/IP. Дополнительных ограничений не вводим.

### 7.6 Безопасность загрузки аватара

- Magic-bytes проверка через Pillow (`Image.verify()`). Если не валидное изображение → **400 Bad Request**.
- Лимит 5 МБ проверяется до чтения в память (через FastAPI `UploadFile` + `Content-Length` или ранний breakpoint при чтении). При превышении → **413 Payload Too Large**.
- После сохранения — повторный `Image.open(saved_path)` для верификации (защита от polyglot-файлов).

---

## 8. Тестирование

### 8.1 Backend (`backend/tests/`)

**Новые файлы:**

- `test_me.py` — личный кабинет:
  - `GET /api/me` возвращает расширенный профиль.
  - `PATCH /api/me` с занятым username → 409.
  - `POST /api/me/avatar` — успешно сохраняет WebP, инкрементит version.
  - `POST /api/me/avatar` с не-картинкой → 400.
  - `DELETE /api/me/avatar` удаляет файл, обнуляет path.
  - `GET /api/me/sessions` возвращает список своих сессий.
  - `DELETE /api/me/sessions` (all) — оставляет только текущую.

- `test_admin_users.py` — управление пользователями + ролевые правила:
  - admin создаёт user → 201; admin создаёт admin → 403.
  - superadmin создаёт любого → 201.
  - admin редактирует superadmin → 403.
  - admin понижает свою роль → 403.
  - superadmin удаляет себя → 403.
  - superadmin удаляет user → soft delete; удалённый не логинится; не показывается без `?include_deleted=true`.
  - PATCH меняет permissions → следующий `GET /auth/me` отражает.
  - reset-password → возвращает пароль один раз, must_change_password=true.

- `test_admin_sessions.py`:
  - `GET /sessions` для admin возвращает все активные.
  - `DELETE /sessions/{id}` устанавливает `kicked_at`, после этого старый access-токен → 401.

- `test_admin_monitoring.py`:
  - `GET /system` от admin → 403, от superadmin → 200 с непустыми CPU/RAM/disk.
  - `GET /stats` агрегирует `usage_today` корректно (создаются 3 пользователя с разными значениями).
  - Версии cache'ируются (второй вызов не запускает subprocess повторно — через мок).

- `test_audit_log.py`:
  - Фильтр по action/user/date работает.
  - Экспорт CSV возвращает корректный заголовок и строки.

- `test_avatars.py`:
  - Upload JPEG → сохранён как WebP размером ≤ 256.
  - Upload файла > 5 МБ → 413.
  - Upload polyglot/некорректного → 400.
  - GET аватара чужого пользователя залогиненным → 200.
  - GET аватара без авторизации → 401.

### 8.2 Frontend e2e (`frontend/tests/`)

В стиле существующих `tests/*.spec.ts`:

- `home.spec.ts`:
  - После логина пользователь попадает на `/`.
  - Видны плитки только для разрешённых модулей.
  - Плитка «Личный кабинет» / «Admin Panel» видна по роли.
  - Клик по плитке ведёт на правильный маршрут.

- `profile.spec.ts`:
  - `/me` показывает username, роль, лимиты.
  - Загрузка аватара через моковый файл, потом удаление.
  - Завершение чужой сессии в списке убирает её.
  - Смена пароля.

- `admin-users.spec.ts`:
  - admin видит таблицу, создаёт user через модалку.
  - При создании показывается одноразовый пароль.
  - admin не видит кнопку «Удалить»; superadmin видит.
  - Edit-модалка изменяет permissions, изменения отражаются после save.

- `admin-monitoring.spec.ts` (для superadmin):
  - Видны карточки CPU/RAM/Disk, цифры > 0.
  - Top-5 пользователей рендерятся.

- `permissions-revoke.spec.ts`:
  - Залогиниваемся как user с permission `image=true`, открываем `/image`.
  - Через API меняем permission на false.
  - Через ≤ 16 секунд polling срабатывает → редирект на `/`.

### 8.3 Что НЕ покрываем

- Pixel-perfect визуальные регрессии аватаров.
- Производительность psutil под нагрузкой.
- CSV-экспорт больших объёмов (фаза 5 для команды 1-5 человек).
- WebSocket/SSE — этого нет в дизайне.

---

## 9. Затронутые/новые файлы (сводка)

### Backend
- **Модифицируются:** `app/models/user.py`, `app/dependencies.py`, `app/routers/admin.py`, `app/routers/auth.py`, `app/main.py`, `app/core/config.py`, `requirements.txt`.
- **Новые:** `app/routers/me.py`, `app/schemas/admin.py`, `app/schemas/me.py`, `app/utils/audit.py`, `app/utils/audit_actions.py`, `app/utils/system_info.py`.
- **Тесты:** `tests/test_me.py`, `tests/test_admin_users.py`, `tests/test_admin_sessions.py`, `tests/test_admin_monitoring.py`, `tests/test_audit_log.py`, `tests/test_avatars.py`.

### Frontend
- **Модифицируются:** `src/App.tsx`, `src/components/Layout/Sidebar.tsx`, `src/components/Layout/Topbar.tsx`, `src/components/ProtectedRoute.tsx`, `src/hooks/useAuthProvider.ts`, `src/types/index.ts`, `src/api/client.ts` (если требуется), `src/pages/Admin/AdminPage.tsx`, `package.json`.
- **Новые:**
  - `src/pages/Home/HomePage.tsx`, `Home.module.css`
  - `src/pages/Profile/ProfilePage.tsx`, `ProfileTab.tsx`, `AvatarUploader.tsx`, `UsageBars.tsx`, `SessionsList.tsx`, `ChangePasswordForm.tsx`, `ChangeUsernameForm.tsx`, `Profile.module.css`
  - `src/pages/Admin/UsersTab.tsx`, `AuditLogTab.tsx`, `MonitoringTab.tsx`, `CreateUserModal.tsx`, `EditUserModal.tsx`, `ResetPasswordModal.tsx`, `ConfirmDeleteModal.tsx`, `Admin.module.css`
  - `src/components/AvatarImage.tsx`
  - `src/hooks/useAuthedImage.ts`
- **Тесты:** `tests/home.spec.ts`, `tests/profile.spec.ts`, `tests/admin-users.spec.ts`, `tests/admin-monitoring.spec.ts`, `tests/permissions-revoke.spec.ts`.

---

## 10. Критерии завершения

- [ ] Главная страница `/` после логина показывает логотип и плитки.
- [ ] Личный кабинет `/me` со всеми блоками (профиль, лимиты, сессии, безопасность).
- [ ] Загрузка/удаление аватара с клиентским кропом, отображение в Topbar / Profile / Admin таблице.
- [ ] Admin Panel с табами Пользователи / Аудит-лог / Мониторинг (superadmin) / Мой профиль.
- [ ] CRUD пользователей с правильными ролевыми проверками (admin не трогает superadmin, не правит себя; superadmin не удаляет себя).
- [ ] Soft-delete пользователя; удалённый не логинится, скрыт из списка.
- [ ] Сброс пароля → одноразовый пароль + `must_change_password = true`.
- [ ] Аудит-лог с фильтрами и экспортом CSV.
- [ ] Активные сессии в `/me` и `/admin`; kill-session инвалидирует access-токен через `kicked_at`.
- [ ] Мониторинг CPU / RAM / Disk / Uptime / версии бинарников; обновление каждые 30 секунд.
- [ ] Расширенная статистика `/api/admin/stats` (downloads/conversions/image_ops_today, top_users, storage).
- [ ] Polling `/auth/me` каждые 15 секунд; смена прав → редирект; деактивация / удаление / kick → logout с toast.
- [ ] Все новые admin actions логируются в audit_log с правильными `details`.
- [ ] Backend-тесты и Playwright-тесты (см. §8) проходят.
- [ ] Мобильная адаптация: главная (1 колонка плиток), Profile (стек блоков), Admin таблицы (горизонтальный скролл или адаптивные карточки).
