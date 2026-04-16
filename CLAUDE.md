# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**NaturalskWeb** — закрытое веб-приложение для малых команд (1–5 чел.) с 4 модулями: скачивание YouTube-видео, конвертация файлов, обработка изображений (удаление фона/водяных знаков) и панель администратора.

Монорепозиторий: `/frontend` (React SPA) + `/backend` (FastAPI).

## Commands

### Frontend (`/frontend`)
```bash
bun run dev        # Dev-сервер Vite на порту 5173 (проксирует /api → localhost:8000)
bun run build      # TypeScript check + сборка Vite
bun run preview    # Предпросмотр production-сборки
bun run lint       # ESLint
npx playwright test            # Все e2e тесты
npx playwright test <file>     # Один тест
```

### Backend (`/backend`)
```bash
uvicorn app.main:app --reload   # Dev-сервер FastAPI на порту 8000
alembic upgrade head            # Применить миграции БД
alembic revision --autogenerate -m "description"  # Создать миграцию
pytest                          # Запуск тестов
pytest tests/test_auth.py       # Один файл тестов
```

## Architecture

### Frontend

**Стек:** React 18 + TypeScript + Vite + React Router 6 + Axios + React Toastify + Lucide React

**Аутентификация:**
- `src/api/client.ts` — Axios-инстанс с перехватчиком 401: автоматически обновляет `access_token` через `refresh_token` и повторяет запрос
- `src/stores/authStore.ts` — глобальный AuthContext + хук `useAuthProvider.ts`
- Токены хранятся в `localStorage` (`access_token`, `refresh_token`)

**Маршруты:**
```
/login            — публичная
/change-password  — смена пароля (флаг must_change_password для новых пользователей)
/youtube          — защищена (permission: youtube)
/converter        — защищена (permission: converter)
/image            — защищена (permission: image)
/admin            — только роли admin/superadmin
```

**Layout:** `MainLayout` (Sidebar + Topbar) оборачивает все защищённые страницы. `ProtectedRoute` проверяет роль и права.

**Типы пользователей:** `user | admin | superadmin` с пермиссиями на каждый модуль и дневными лимитами использования.

### Backend

**Стек:** FastAPI + SQLAlchemy 2.0 (ORM) + SQLite + Alembic + PyJWT + APScheduler + yt-dlp + FFmpeg + LibreOffice + rembg (u2netp) + Pillow + OpenCV

**Структура `/backend/app`:**
- `models/` — SQLAlchemy-модели (user, session, audit_log)
- `schemas/` — Pydantic v2 схемы запросов/ответов
- `routers/` — эндпоинты (auth, youtube, convert, image, admin)
- `services/` — бизнес-логика
- `core/` — утилиты ядра (конфиг, JWT, зависимости)
- `middleware/` — CORS, auth middleware
- `utils/` — вспомогательные функции

**Хранилище:** база SQLite в `/backend/data/`, временные файлы в `/backend/uploads/` (TTL 6 ч, чистятся APScheduler-ом).

### Production

Backend раздаёт собранный `/frontend/dist`. Vite-прокси `/api → localhost:8000` работает только в dev-режиме.

## Spec

В `/spec/` хранятся технические спецификации по фазам разработки (`overview.md`, `phase-1.md` … `phase-6.md`) на русском языке — читай их для понимания требований к фичам.
