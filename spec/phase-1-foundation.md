# Фаза 1 — Foundation (Фундамент)

> Цель: создать базовую инфраструктуру проекта, систему аутентификации, общий layout и дизайн-систему.

---

## 🔧 Backend

### 1.1 Инициализация проекта
- [ ] Создать структуру папок `backend/app/`
- [ ] Настроить `requirements.txt` с зависимостями:
  ```
  fastapi>=0.110.0
  uvicorn[standard]>=0.27.0
  sqlalchemy>=2.0.0
  alembic>=1.13.0
  pyjwt>=2.8.0
  passlib[bcrypt]>=1.7.4
  python-dotenv>=1.0.0
  python-multipart>=0.0.6
  pydantic>=2.0.0
  pydantic-settings>=2.0.0
  apscheduler>=3.10.0
  aiosqlite>=0.19.0
  ```
- [ ] Создать `.env.example`:
  ```env
  SECRET_KEY=your-secret-key-change-this
  JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
  JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
  DATABASE_URL=sqlite+aiosqlite:///./data/naturalsk.db
  UPLOAD_DIR=./uploads
  FILE_TTL_HOURS=6
  MAX_LOGIN_ATTEMPTS=5
  LOGIN_LOCKOUT_MINUTES=15
  CORS_ORIGINS=http://localhost:5173
  ```

### 1.2 Конфигурация (`app/config.py`)
- [ ] Pydantic Settings для загрузки переменных из `.env`
- [ ] Валидация всех параметров при старте

### 1.3 База данных (`app/database.py`)
- [ ] Async SQLAlchemy engine для SQLite
- [ ] Session factory с async context manager
- [ ] Dependency для FastAPI (`get_db`)
- [ ] Создание папки `data/` при первом запуске

### 1.4 Модели данных (`app/models/`)

#### `user.py`
```python
class User:
    id: int (PK, autoincrement)
    username: str (unique, indexed)
    password_hash: str
    role: str  # 'superadmin', 'admin', 'user'
    is_active: bool (default=True)
    must_change_password: bool (default=True)
    permissions: JSON  # {"youtube": true, "converter": true, "image": true}
    limits: JSON  # {"youtube_daily": 50, "convert_daily": 100, "image_daily": 50}
    usage_today: JSON  # {"youtube": 0, "converter": 0, "image": 0}
    usage_reset_date: date
    created_at: datetime
    updated_at: datetime
    last_login: datetime (nullable)
    failed_login_attempts: int (default=0)
    locked_until: datetime (nullable)
```

#### `audit_log.py`
```python
class AuditLog:
    id: int (PK)
    user_id: int (FK -> User, nullable)
    action: str  # 'login', 'login_failed', 'download', 'convert', etc.
    details: JSON  # Детали действия
    ip_address: str
    user_agent: str
    created_at: datetime
```

#### `active_session.py`
```python
class ActiveSession:
    id: int (PK)
    user_id: int (FK -> User)
    token_jti: str (unique)  # JWT ID для отзыва
    ip_address: str
    user_agent: str
    created_at: datetime
    expires_at: datetime
```

### 1.5 Alembic миграции
- [ ] Инициализировать Alembic: `alembic init alembic`
- [ ] Настроить `alembic.ini` для SQLite
- [ ] Создать начальную миграцию

### 1.6 Система аутентификации (`app/routers/auth.py`)

#### Эндпоинты:
| Метод | URL | Описание | Auth |
|-------|-----|---------|------|
| POST | `/api/auth/login` | Вход по логину/паролю | ❌ |
| POST | `/api/auth/refresh` | Обновление access токена | 🔄 refresh |
| POST | `/api/auth/logout` | Выход (отзыв токена) | ✅ |
| POST | `/api/auth/change-password` | Смена пароля | ✅ |
| GET  | `/api/auth/me` | Текущий пользователь | ✅ |

#### Логика:
- `POST /login`:
  1. Проверить блокировку аккаунта (locked_until)
  2. Найти пользователя по username
  3. Проверить пароль через bcrypt
  4. При неудаче: инкрементировать failed_login_attempts, записать аудит-лог
  5. При 5 неудачах: заблокировать на 15 минут
  6. При успехе: сбросить счётчик, создать JWT access + refresh токены
  7. Записать active_session
  8. Записать аудит-лог
  9. Вернуть токены + флаг `must_change_password`

- `POST /change-password`:
  1. Проверить текущий пароль
  2. Валидировать новый пароль (мин. 8 символов, буквы + цифры)
  3. Обновить hash
  4. Установить `must_change_password = False`

### 1.7 Middleware (`app/middleware/`)

#### `auth.py` — JWT middleware
- Извлечение токена из `Authorization: Bearer <token>`
- Проверка подписи, срока действия, наличия в active_sessions
- Добавление `request.state.user` для следующих handlers

#### `rate_limit.py` — Rate Limiter
- In-memory хранилище (dict с TTL)
- Лимиты: 60 req/min для обычных, 10 req/min для auth
- Возвращать `429 Too Many Requests` при превышении

#### `logging.py` — Request Logger
- Логирование каждого запроса: метод, путь, IP, время выполнения
- Формат: `[2024-01-01 12:00:00] POST /api/auth/login 200 45ms 192.168.1.1`

### 1.8 Утилиты (`app/utils/`)

#### `security.py`
- `hash_password(password) -> str`
- `verify_password(password, hash) -> bool`
- `create_access_token(data, expires) -> str`
- `create_refresh_token(data, expires) -> str`
- `decode_token(token) -> dict`
- `generate_random_password(length=12) -> str`

#### `file_cleanup.py`
- `cleanup_old_files(upload_dir, max_age_hours=6)`
- Вызывается по расписанию через APScheduler каждые 30 минут

### 1.9 Инициализация суперадмина (`app/main.py` — startup event)
- [ ] При первом запуске (если нет пользователей в БД):
  1. Создать пользователя `admin` с ролью `superadmin`
  2. Сгенерировать случайный пароль
  3. Установить `must_change_password = True`
  4. Вывести в консоль:
     ```
     ╔══════════════════════════════════════╗
     ║   NaturalskWeb — First Launch        ║
     ║                                      ║
     ║   Superadmin created:                ║
     ║   Username: admin                    ║
     ║   Password: aB3$kL9mPx2Q            ║
     ║                                      ║
     ║   Change this password on first      ║
     ║   login!                             ║
     ╚══════════════════════════════════════╝
     ```

### 1.10 APScheduler — Планировщик
- [ ] Задача `cleanup_expired_files` — каждые 30 минут
- [ ] Задача `reset_daily_usage` — каждый день в 00:00
- [ ] Запуск при старте FastAPI (lifespan)

---

## 🎨 Frontend

### 1.11 Инициализация проекта
- [ ] Создать React проект через Vite: `npm create vite@latest frontend -- --template react-ts`
- [ ] Установить зависимости:
  ```
  react-router-dom
  axios
  lucide-react
  react-toastify
  ```
- [ ] Настроить `vite.config.ts`:
  - Proxy для API: `/api` -> `http://localhost:8000`

### 1.12 Дизайн-система (`src/styles/`)

#### `variables.css` — CSS переменные
- Полная цветовая палитра (военно-чёрный стиль)
- Размеры шрифтов, отступов, радиусов
- Breakpoints для responsive

#### `global.css` — Глобальные стили
- Reset / Normalize
- Базовые стили body, scrollbar, selection
- Шрифты: Inter (UI) + JetBrains Mono (данные)

#### `theme.css` — Компоненты дизайна
- Утилитарные классы для карточек, кнопок, инпутов
- Анимации: fade-in, slide-up, pulse

### 1.13 Компонент звёздного неба (`src/components/StarryBackground/`)
- [ ] Canvas-based анимация с использованием requestAnimationFrame
- [ ] 200–400 звёзд разного размера (1–3px)
- [ ] Мерцание с разной частотой
- [ ] Редкие «падающие звёзды»
- [ ] Полностью адаптивный (resize handler)
- [ ] Оптимизированный для слабого железа (GPU-ускорение через CSS `will-change`)

### 1.14 Layout (`src/components/Layout/`)
- [ ] Sidebar с навигацией (иконки + текст)
  - YouTube Downloader
  - File Converter
  - Image Processor
  - Admin Panel (только для admin/superadmin)
- [ ] Header с:
  - Название приложения "NaturalskWeb"
  - Текущий пользователь
  - Кнопка выхода
- [ ] Adaptive: sidebar превращается в bottom bar на мобильных

### 1.15 Страница входа (`src/pages/Login/`)
- [ ] Центрированная форма на фоне звёздного неба
- [ ] Поля: username, password
- [ ] Кнопка "Войти" с loading состоянием
- [ ] Отображение ошибок (неверный пароль, аккаунт заблокирован)
- [ ] Логотип "NaturalskWeb" сверху

### 1.16 Страница смены пароля (`src/pages/ChangePassword/`)
- [ ] Появляется принудительно, если `must_change_password = true`
- [ ] Поля: текущий пароль, новый пароль, подтверждение
- [ ] Валидация: мин. 8 символов, буквы + цифры
- [ ] Индикатор сложности пароля

### 1.17 Protected Route (`src/components/ProtectedRoute/`)
- [ ] Проверка наличия JWT токена
- [ ] Проверка `must_change_password` → редирект на смену пароля
- [ ] Проверка прав доступа к конкретной странице
- [ ] Redirect на `/login` при отсутствии токена

### 1.18 API клиент (`src/api/client.ts`)
- [ ] Axios instance с baseURL
- [ ] Interceptor для вставки JWT в заголовки
- [ ] Interceptor для автоматического refresh токена при 401
- [ ] Обработка ошибок сети

### 1.19 Роутинг (`src/App.tsx`)
```
/login                 → Login
/change-password       → ChangePassword
/youtube               → YouTubeDownloader     (требует permission)
/converter             → FileConverter         (требует permission)
/image                 → ImageProcessor        (требует permission)
/admin                 → AdminPanel            (только admin/superadmin)
```

---

## ✅ Критерии завершения Phase 1

- [ ] Backend стартует, создаёт суперадмина, выводит пароль в консоль
- [ ] Можно залогиниться через API и получить JWT
- [ ] Frontend отображает страницу логина со звёздным небом
- [ ] После логина видно layout с sidebar и пустыми страницами
- [ ] Принудительная смена пароля работает
- [ ] Rate limiter блокирует при превышении лимита
- [ ] Файлы автоматически удаляются через 6 часов
- [ ] Responsive: корректно отображается на мобильных
