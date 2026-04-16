# NaturalskWeb — Общий обзор и архитектура

## Описание проекта

**NaturalskWeb** — закрытое мульти-инструментальное веб-приложение для маленькой команды (1–5 человек). Включает 4 основных модуля: загрузка видео с YouTube, конвертация файлов, обработка изображений (удаление фона/водяных знаков) и админ-панель с мониторингом.

## Технологический стек

### Backend
| Компонент | Технология | Версия |
|-----------|-----------|--------|
| Framework | FastAPI | 0.110+ |
| Python | CPython | 3.11+ |
| ORM | SQLAlchemy | 2.0+ |
| Миграции | Alembic | 1.13+ |
| БД | SQLite | 3.x |
| Auth | JWT (PyJWT) | — |
| Фоновые задачи | asyncio + BackgroundTasks | — |
| YouTube | yt-dlp | latest |
| Конвертация медиа | FFmpeg (через subprocess) | 6.x+ |
| Конвертация документов | LibreOffice (headless) | 7.x+ |
| Обработка изображений | rembg (u2netp), Pillow, OpenCV | — |
| Валидация | Pydantic v2 | 2.x |
| Хэширование паролей | bcrypt (passlib) | — |
| Планировщик | APScheduler | 3.x |

### Frontend
| Компонент | Технология | Версия |
|-----------|-----------|--------|
| Framework | React | 18+ |
| Сборщик | Vite | 5+ |
| Язык | TypeScript | 5+ |
| Роутинг | React Router | 6+ |
| HTTP-клиент | Axios | — |
| Стили | CSS Modules + CSS Variables | — |
| Анимации | Canvas API (звёздное небо) | — |
| Иконки | Lucide React | — |
| Уведомления | React Toastify | — |

## Архитектура приложения

```
┌─────────────────────────────────────────────────┐
│                   NGINX / Reverse Proxy          │
│                 (HTTPS, Rate Limiting)           │
├──────────────────┬──────────────────────────────┤
│   React SPA      │       FastAPI Backend         │
│   (Vite build)   │                              │
│   Port: 3000     │       Port: 8000             │
│                  │                              │
│  ┌────────────┐  │  ┌──────────────────────┐    │
│  │ Pages:     │  │  │ API Routes:          │    │
│  │ - Login    │  │  │ /api/auth/*          │    │
│  │ - YouTube  │◄─┼─►│ /api/youtube/*       │    │
│  │ - Convert  │  │  │ /api/convert/*       │    │
│  │ - Image    │  │  │ /api/image/*         │    │
│  │ - Admin    │  │  │ /api/admin/*         │    │
│  └────────────┘  │  └──────┬───────────────┘    │
│                  │         │                    │
│                  │  ┌──────▼───────────────┐    │
│                  │  │ Services Layer       │    │
│                  │  │ - AuthService        │    │
│                  │  │ - YouTubeService     │    │
│                  │  │ - ConvertService     │    │
│                  │  │ - ImageService       │    │
│                  │  │ - AdminService       │    │
│                  │  └──────┬───────────────┘    │
│                  │         │                    │
│                  │  ┌──────▼───────────────┐    │
│                  │  │ SQLite + File System │    │
│                  │  │ uploads/ (6h TTL)    │    │
│                  │  └─────────────────────┘    │
└─────────────────────────────────────────────────┘
```

## Структура проекта

```
NaturalskWeb/
├── spec/                          # Спецификации (этот файл)
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                # FastAPI app, startup events
│   │   ├── config.py              # Настройки (.env)
│   │   ├── database.py            # SQLAlchemy + SQLite
│   │   ├── models/                # SQLAlchemy модели
│   │   │   ├── user.py
│   │   │   ├── session.py
│   │   │   └── audit_log.py
│   │   ├── schemas/               # Pydantic схемы
│   │   │   ├── auth.py
│   │   │   ├── user.py
│   │   │   ├── youtube.py
│   │   │   ├── convert.py
│   │   │   └── image.py
│   │   ├── routers/               # API endpoints
│   │   │   ├── auth.py
│   │   │   ├── youtube.py
│   │   │   ├── convert.py
│   │   │   ├── image.py
│   │   │   └── admin.py
│   │   ├── services/              # Бизнес-логика
│   │   │   ├── auth_service.py
│   │   │   ├── youtube_service.py
│   │   │   ├── convert_service.py
│   │   │   ├── image_service.py
│   │   │   └── admin_service.py
│   │   ├── middleware/            # Middleware
│   │   │   ├── auth.py
│   │   │   ├── rate_limit.py
│   │   │   └── logging.py
│   │   ├── utils/                 # Утилиты
│   │   │   ├── security.py
│   │   │   ├── file_cleanup.py
│   │   │   └── validators.py
│   │   └── tasks/                 # Фоновые задачи
│   │       ├── cleanup.py
│   │       └── scheduler.py
│   ├── uploads/                   # Временные файлы (6h TTL)
│   ├── data/                      # SQLite DB файл
│   ├── requirements.txt
│   ├── .env.example
│   └── alembic/                   # Миграции
├── frontend/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── api/                   # Axios клиент
│   │   │   └── client.ts
│   │   ├── hooks/                 # Кастомные хуки
│   │   ├── components/            # Общие компоненты
│   │   │   ├── Layout/
│   │   │   ├── StarryBackground/
│   │   │   ├── Sidebar/
│   │   │   └── ProtectedRoute/
│   │   ├── pages/
│   │   │   ├── Login/
│   │   │   ├── ChangePassword/
│   │   │   ├── YouTube/
│   │   │   ├── Converter/
│   │   │   ├── ImageProcessor/
│   │   │   └── Admin/
│   │   ├── store/                 # Состояние (zustand/context)
│   │   ├── styles/                # Глобальные стили
│   │   │   ├── variables.css
│   │   │   ├── global.css
│   │   │   └── theme.css
│   │   └── types/                 # TypeScript типы
│   ├── public/
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── package.json
└── README.md
```

## Дизайн-система

### Цветовая палитра (военно-чёрный стиль)
```css
--color-bg-primary:    #0a0a0f;     /* Основной фон */
--color-bg-secondary:  #12121a;     /* Вторичный фон */
--color-bg-card:       #1a1a2e;     /* Карточки */
--color-bg-hover:      #252540;     /* Hover */
--color-border:        #2a2a3e;     /* Границы */
--color-border-focus:  #4a4a6a;     /* Активная граница */
--color-text-primary:  #e0e0e8;     /* Основной текст */
--color-text-secondary:#8888a0;     /* Вторичный текст */
--color-accent:        #5865F2;     /* Акцент (синий) */
--color-accent-hover:  #4752C4;     /* Акцент hover */
--color-success:       #43b581;     /* Успех */
--color-warning:       #faa61a;     /* Предупреждение */
--color-danger:        #f04747;     /* Опасность */
--color-star:          #ffffff;     /* Звёзды */
--color-star-glow:     #6e7bff33;  /* Свечение звёзд */
```

### Типографика
```
Шрифт: 'JetBrains Mono' (код/данные), 'Inter' (UI)
Размеры: 12px / 14px / 16px / 20px / 24px / 32px
```

## Безопасность

- JWT access + refresh токены
- Bcrypt хэширование паролей
- Rate limiting на все эндпоинты
- CORS настроен только для своего домена
- Защита от брутфорса (блокировка после 5 попыток на 15 мин)
- CSP (Content Security Policy) заголовки
- HTTPS через NGINX
- Input validation на всех уровнях
- Аудит-лог всех действий
- Автоочистка файлов каждые 30 минут (удаление файлов старше 6 часов)

## Лог решений (Decision Log)

| # | Решение | Альтернативы | Причина выбора |
|---|---------|-------------|----------------|
| 1 | FastAPI | Django, Flask | Async из коробки, auto-docs, Pydantic |
| 2 | SQLite | PostgreSQL, MySQL | Для 1–5 пользователей overkill держать отдельный сервер БД |
| 3 | React + Vite | Next.js, Vue | SPA достаточно, SSR не нужен |
| 4 | yt-dlp | youtube-dl | Активно поддерживается, больше фич |
| 5 | rembg (u2netp) | u2net, API | Работает на слабом железе, оффлайн |
| 6 | JWT | Sessions | Stateless, масштабируемо |
| 7 | APScheduler | Celery, cron | Лёгкий, встроен в процесс, не нужен Redis |
| 8 | CSS Modules | Tailwind, styled-components | Полный контроль стилей для кастомного военного дизайна |

## Фазы реализации

| Фаза | Название | Описание | Зависимости |
|------|---------|---------|-------------|
| 1 | Foundation | Структура проекта, auth, layout, дизайн-система | — |
| 2 | YouTube Downloader | Загрузка видео/плейлистов | Phase 1 |
| 3 | File Converter | Конвертация медиа + документов | Phase 1 |
| 4 | Image Processor | Удаление фона/watermark | Phase 1 |
| 5 | Admin & Monitoring | Управление пользователями, мониторинг | Phase 1 |
| 6 | Security & Deploy | Hardening, тесты, деплой на VPS | Phase 1–5 |
