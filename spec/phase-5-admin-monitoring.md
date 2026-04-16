# Фаза 5 — Admin & Monitoring (Админка и мониторинг)

> Цель: управление пользователями, правами, лимитами + мониторинг системы и активности.

---

## 🔧 Backend

### 5.1 API роутер (`app/routers/admin.py`)

Все эндпоинты требуют роль `admin` или `superadmin`.

#### Управление пользователями:
| Метод | URL | Описание |
|-------|-----|---------|
| GET | `/api/admin/users` | Список пользователей (с пагинацией, фильтрацией) |
| POST | `/api/admin/users` | Создать пользователя |
| GET | `/api/admin/users/{id}` | Детали пользователя |
| PATCH | `/api/admin/users/{id}` | Обновить пользователя |
| DELETE | `/api/admin/users/{id}` | Деактивировать (soft delete) |
| POST | `/api/admin/users/{id}/reset-password` | Сбросить пароль (сгенерировать новый) |
| POST | `/api/admin/users/{id}/toggle-active` | Вкл/выкл аккаунт |

#### Мониторинг:
| Метод | URL | Описание |
|-------|-----|---------|
| GET | `/api/admin/stats` | Общая статистика |
| GET | `/api/admin/audit-log` | Аудит-лог (пагинация, фильтры) |
| GET | `/api/admin/sessions` | Активные сессии |
| DELETE | `/api/admin/sessions/{id}` | Принудительный выход пользователя |
| GET | `/api/admin/system` | Системная информация |
| GET | `/api/admin/storage` | Статус хранилища (размер, файлов) |

### 5.2 Создание пользователя
```python
class CreateUserRequest:
    username: str          # 3-32 символа, a-z, 0-9, _
    role: str              # 'user' или 'admin'
    permissions: dict      # {"youtube": true, "converter": true, "image": true}
    limits: dict           # {"youtube_daily": 50, "convert_daily": 100, "image_daily": 50}
```
- Генерация случайного пароля
- `must_change_password = True`
- Вернуть пароль в ответе (однократно)

### 5.3 Статистика (`/api/admin/stats`)
```python
class SystemStats:
    total_users: int
    active_users: int
    total_downloads_today: int
    total_conversions_today: int
    total_image_ops_today: int
    storage_used_mb: float
    active_sessions: int
    top_users: list[UserUsageStats]  # Топ-5 по активности
```

### 5.4 Системная информация (`/api/admin/system`)
```python
class SystemInfo:
    cpu_percent: float
    ram_used_mb: float
    ram_total_mb: float
    disk_used_gb: float
    disk_total_gb: float
    uptime_seconds: int
    python_version: str
    ffmpeg_version: str
    yt_dlp_version: str
```
Получается через `psutil` (добавить в зависимости).

### 5.5 Аудит-лог
- Фильтры: по пользователю, действию, дате, IP
- Пагинация: offset + limit
- Экспорт в CSV (опционально)

### 5.6 Ролевая модель

| Право | user | admin | superadmin |
|-------|------|-------|------------|
| Использовать YouTube/Convert/Image | ✓ (если разрешено) | ✓ | ✓ |
| Смотреть свой профиль | ✓ | ✓ | ✓ |
| Менять свой пароль | ✓ | ✓ | ✓ |
| Видеть список пользователей | ✗ | ✓ | ✓ |
| Создавать пользователей | ✗ | ✓ (только user) | ✓ (любые) |
| Удалять пользователей | ✗ | ✗ | ✓ |
| Видеть аудит-лог | ✗ | ✓ | ✓ |
| Видеть системную информацию | ✗ | ✗ | ✓ |

---

## 🎨 Frontend

### 5.7 Страница админки (`src/pages/Admin/`)

**`AdminPage.tsx`** — layout с табами:
- Пользователи
- Аудит-лог  
- Мониторинг (только superadmin)

**`UsersTab.tsx`** — таблица пользователей
- Колонки: username, роль, статус, создан, последний вход, использование сегодня
- Кнопки: создать, редактировать, сбросить пароль, деактивировать
- Модальное окно создания пользователя с настройкой permissions/limits

**`AuditLogTab.tsx`** — таблица логов
- Колонки: дата, пользователь, действие, детали, IP
- Фильтры сверху: поиск, выбор действия, диапазон дат
- Бесконечный скролл или пагинация

**`MonitoringTab.tsx`** — системная информация
- Карточки: CPU, RAM, Disk, Uptime
- Простые bar-графики использования
- Счётчики операций за сегодня
- Обновление каждые 30 секунд

**`CreateUserModal.tsx`** — модальное окно
- Username (валидация)
- Роль (dropdown)
- Чекбоксы permissions
- Числовые поля limits
- Показать сгенерированный пароль после создания

---

## ✅ Критерии завершения
- [ ] CRUD пользователей (создание, редактирование, деактивация)
- [ ] Настройка permissions и limits для каждого пользователя
- [ ] Сброс пароля → генерация нового + must_change_password
- [ ] Аудит-лог с фильтрацией и пагинацией
- [ ] Мониторинг CPU/RAM/Disk в реальном времени
- [ ] Ролевая модель работает корректно
- [ ] Мобильная адаптация таблиц
