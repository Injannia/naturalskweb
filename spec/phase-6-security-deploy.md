# Фаза 6 — Security & Deploy (Безопасность и деплой)

> Цель: финальное hardening, оптимизация, тестирование и подготовка к деплою на VPS.

---

## 🔧 Backend

### 6.1 Security Hardening

**CORS:**
- Разрешить только конкретный домен из `.env`
- Запретить `*` в production

**Заголовки безопасности (middleware):**
```python
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
Content-Security-Policy: default-src 'self'; img-src 'self' data: https://i.ytimg.com;
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

**Input Validation:**
- Все входные данные через Pydantic
- Длина строк ограничена
- URL-валидация для YouTube ссылок
- Запрет path traversal в именах файлов

**Rate Limiting (финальная настройка):**
- `/api/auth/login`: 10 req/min
- `/api/youtube/*`: 30 req/min  
- `/api/convert/*`: 30 req/min
- `/api/image/*`: 20 req/min
- `/api/admin/*`: 60 req/min

**Логирование:**
- Structured JSON logging (python-json-logger)
- Ротация логов (max 50MB, 5 файлов)
- Уровни: ERROR → файл, WARNING → файл, INFO → stdout

### 6.2 Оптимизация производительности
- Кэширование YouTube info (in-memory, TTL 5 мин)
- Async file I/O  
- Streaming file downloads (не загружать в память целиком)
- gzip compression middleware

### 6.3 Автоочистка файлов (финальная версия)
- APScheduler: каждые 30 мин сканировать `uploads/`
- Удалять папки старше 6 часов
- Логировать удалённые файлы
- Graceful: не удалять файлы с активными задачами

---

## 🎨 Frontend

### 6.4 Финальная оптимизация
- Code splitting (lazy loading страниц через React.lazy)
- Минимизация бандла через Vite
- Оптимизация изображений
- Service Worker для offline shell (опционально)

### 6.5 Meta-теги и SEO
- Title: "NaturalskWeb"
- Favicon
- manifest.json для PWA-like опыта

### 6.6 Error Boundaries
- Глобальный ErrorBoundary (ловит React crashes)
- Красивая страница ошибки в стиле дизайна

---

## 🚀 Деплой

### 6.7 Docker
```dockerfile
# Backend
FROM python:3.11-slim
RUN apt-get update && apt-get install -y ffmpeg libreoffice-writer
COPY backend/ /app/
RUN pip install -r requirements.txt
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Frontend  
FROM node:20-slim AS builder
COPY frontend/ /app/
RUN npm ci && npm run build
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
```

### 6.8 docker-compose.yml
```yaml
services:
  backend:
    build: ./backend
    ports: ["8000:8000"]
    volumes:
      - ./data:/app/data
      - ./uploads:/app/uploads
    env_file: .env

  frontend:
    build: ./frontend
    ports: ["80:80"]
    depends_on: [backend]
```

### 6.9 NGINX конфигурация
- HTTPS (Let's Encrypt / certbot)
- Proxy pass `/api` → backend:8000
- Serve frontend static files
- Rate limiting на уровне NGINX
- gzip compression

### 6.10 Скрипт деплоя
- `deploy.sh` — pull, build, restart docker-compose
- Backup SQLite перед обновлением

---

## ✅ Критерии завершения
- [ ] Все заголовки безопасности установлены
- [ ] Rate limiting настроен по уровням
- [ ] Файлы автоудаляются через 6 часов
- [ ] Docker сборка работает
- [ ] NGINX + HTTPS настроен
- [ ] Приложение работает стабильно 24/7
