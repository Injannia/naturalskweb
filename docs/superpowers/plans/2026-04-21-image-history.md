# Image Processor History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Привести UX истории файлов на странице Image Processor в соответствие с File Converter — полноценные секции «Активные задачи» и «История» с thumbnail-карточками, page-level polling, dismiss / restore / permanent-delete / bulk-hide, resume-after-reload.

**Architecture:** Подход 1 — полное зеркало архитектуры `ConverterPage`. Состояние списков задач и polling переезжают из дочерних редакторов (`BackgroundRemoval`, `WatermarkRemoval`) в `ImageProcessorPage`. Новый компонент `ImageProgress` (аналог `ConvertProgress`) с thumbnail-превью реюзается для активных задач и для истории. На бэкенде добавляется единственный endpoint `DELETE /api/image/task/{id}/permanent`. На фронте настраивается Vitest + unit-тесты для `ImageProgress` и `Thumbnail`.

**Tech Stack:** FastAPI · SQLAlchemy · pytest · React 18 · TypeScript · Vite · Vitest · @testing-library/react · @testing-library/jest-dom · jsdom

**Spec:** `docs/superpowers/specs/2026-04-21-image-history-design.md`

---

## File Structure

**Backend — создаётся:**
- `backend/tests/test_image_permanent_delete.py` — тесты для `image_service.delete_task_permanent`

**Backend — изменяется:**
- `backend/app/services/image_service.py` — новая функция `delete_task_permanent`
- `backend/app/routers/image.py` — новый endpoint `DELETE /api/image/task/{task_id}/permanent`

**Frontend test infrastructure — создаётся:**
- `frontend/src/test/setup.ts` — setup-файл Vitest со стабом `IntersectionObserver`

**Frontend test infrastructure — изменяется:**
- `frontend/package.json` — devDependencies для Vitest + Testing Library, скрипты `test` / `test:run`
- `frontend/vite.config.ts` — `test` блок (environment: jsdom, setupFiles)
- `frontend/tsconfig.json` — `types: ["vitest/globals", "@testing-library/jest-dom"]`

**Frontend компоненты — создаётся:**
- `frontend/src/pages/ImageProcessor/components/Thumbnail.tsx` — lazy-thumbnail с IntersectionObserver + blob URL lifecycle
- `frontend/src/pages/ImageProcessor/components/Thumbnail.module.css` — стили
- `frontend/src/pages/ImageProcessor/components/Thumbnail.test.tsx` — unit-тесты
- `frontend/src/pages/ImageProcessor/components/ImageProgress.tsx` — карточка задачи (аналог `ConvertProgress`)
- `frontend/src/pages/ImageProcessor/components/ImageProgress.module.css` — стили
- `frontend/src/pages/ImageProcessor/components/ImageProgress.test.tsx` — unit-тесты

**Frontend — изменяется:**
- `frontend/src/pages/ImageProcessor/imageApi.ts` — добавить `deleteTaskPermanent`
- `frontend/src/pages/ImageProcessor/ImageProcessorPage.tsx` — полный рефактор: списки, polling, handlers
- `frontend/src/pages/ImageProcessor/components/BackgroundRemoval.tsx` — принять `currentTask` через props, убрать локальный polling
- `frontend/src/pages/ImageProcessor/components/WatermarkRemoval.tsx` — то же
- `frontend/src/pages/ImageProcessor/ImageProcessorPage.module.css` — добавить стили секций `tasksSection`, `historySection` по образцу Converter

**Frontend — удаляется:**
- `frontend/src/pages/ImageProcessor/components/TaskHistory.tsx`
- `frontend/src/pages/ImageProcessor/components/TaskHistory.module.css`

---

### Task 0: Backend — функция `delete_task_permanent` в `image_service`

**Goal:** Добавить сервисную функцию, которая удаляет `ImageTask` и его файлы с диска, с проверкой ownership и terminal-статуса.

**Files:**
- Modify: `backend/app/services/image_service.py` (добавить функцию после `restore_task` на строке 901)
- Create: `backend/tests/test_image_permanent_delete.py`

**Acceptance Criteria:**
- [ ] Функция `delete_task_permanent(task_id, user_id, db)` возвращает `True` при успехе, `False` если задача не найдена, чужая, или не в terminal-статусе
- [ ] При успехе: `uploads/{task_id}/` удаляется через `shutil.rmtree(ignore_errors=True)`, запись из `_active_tasks` убирается под `_tasks_lock`, строка `ImageTask` удаляется из БД
- [ ] Тесты проходят: happy path, чужая задача, несуществующая, non-terminal статус

**Verify:** `cd backend && pytest tests/test_image_permanent_delete.py -v` → 4 PASSED

**Steps:**

- [ ] **Step 1: Написать тесты**

Create `backend/tests/test_image_permanent_delete.py`:

```python
"""Tests for image_service.delete_task_permanent."""
import os
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text

from app.core.database import Base
from app.models.image_task import ImageTask
from app.services import image_service


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = OFF"))
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _make_task(
    db: AsyncSession,
    *,
    user_id: int = 1,
    status: str = "ready",
    hidden: bool = False,
) -> ImageTask:
    task = ImageTask(
        id=str(uuid.uuid4()),
        user_id=user_id,
        original_filename="test.png",
        original_ext="png",
        operation="remove_bg",
        status=status,
        progress=100 if status == "ready" else 0,
        hidden=hidden,
        filename="result.png" if status == "ready" else None,
        file_size=1024 if status == "ready" else None,
        inpaint_method=None,
        error=None,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
        completed_at=datetime.now(timezone.utc).replace(tzinfo=None) if status == "ready" else None,
    )
    db.add(task)
    await db.commit()
    return task


@pytest.mark.asyncio
async def test_delete_permanent_happy_path(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(image_service.settings, "UPLOAD_DIR", str(tmp_path))
    task = await _make_task(db_session)
    task_dir = tmp_path / task.id
    task_dir.mkdir()
    (task_dir / "result.png").write_bytes(b"\x89PNG\x00")

    result = await image_service.delete_task_permanent(
        task_id=task.id, user_id=1, db=db_session,
    )
    assert result is True
    assert not task_dir.exists()
    # DB row gone
    from sqlalchemy import select
    found = (await db_session.execute(select(ImageTask).where(ImageTask.id == task.id))).scalar_one_or_none()
    assert found is None


@pytest.mark.asyncio
async def test_delete_permanent_wrong_user(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(image_service.settings, "UPLOAD_DIR", str(tmp_path))
    task = await _make_task(db_session, user_id=1)
    result = await image_service.delete_task_permanent(
        task_id=task.id, user_id=2, db=db_session,
    )
    assert result is False
    # DB row intact
    from sqlalchemy import select
    found = (await db_session.execute(select(ImageTask).where(ImageTask.id == task.id))).scalar_one_or_none()
    assert found is not None


@pytest.mark.asyncio
async def test_delete_permanent_nonexistent(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(image_service.settings, "UPLOAD_DIR", str(tmp_path))
    result = await image_service.delete_task_permanent(
        task_id="does-not-exist", user_id=1, db=db_session,
    )
    assert result is False


@pytest.mark.asyncio
async def test_delete_permanent_rejects_non_terminal_status(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(image_service.settings, "UPLOAD_DIR", str(tmp_path))
    task = await _make_task(db_session, status="processing")
    result = await image_service.delete_task_permanent(
        task_id=task.id, user_id=1, db=db_session,
    )
    assert result is False
```

- [ ] **Step 2: Запустить тесты — убедиться, что они падают**

Run: `cd backend && pytest tests/test_image_permanent_delete.py -v`
Expected: FAIL с `AttributeError: module 'app.services.image_service' has no attribute 'delete_task_permanent'`

- [ ] **Step 3: Добавить функцию в `image_service.py`**

В `backend/app/services/image_service.py` вставить **после** `restore_task` (после строки 901):

```python
async def delete_task_permanent(
    task_id: str, user_id: int, db: AsyncSession
) -> bool:
    """Permanently delete a task — removes file from disk and DB record.

    Only allowed for terminal tasks (ready/error). If files are already
    cleaned up, only the DB record is removed.

    Returns True if found and deleted, False otherwise.
    """
    row = await get_task_for_user(task_id, user_id, db)
    if row is None:
        return False
    if row.status not in TERMINAL_STATUSES:
        return False

    # Remove files from disk
    task_dir = os.path.join(settings.UPLOAD_DIR, task_id)
    shutil.rmtree(task_dir, ignore_errors=True)

    # Remove from in-memory cache
    with _tasks_lock:
        _active_tasks.pop(task_id, None)

    # Remove DB row
    await db.delete(row)
    await db.commit()
    logger.info("Image task %s permanently deleted by user %d", task_id, user_id)
    return True
```

Проверить, что импорты `shutil`, `os`, `TERMINAL_STATUSES`, `_tasks_lock`, `_active_tasks`, `get_task_for_user`, `settings`, `logger` уже есть в модуле (они используются другими функциями). Если `shutil` не импортирован — добавить `import shutil` в шапку.

- [ ] **Step 4: Запустить тесты снова**

Run: `cd backend && pytest tests/test_image_permanent_delete.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Убедиться, что остальные тесты не сломались**

Run: `cd backend && pytest tests/ -v`
Expected: все существующие тесты PASSED + 4 новых PASSED

- [ ] **Step 6: Коммит**

```bash
git add backend/app/services/image_service.py backend/tests/test_image_permanent_delete.py
git commit -m "feat(image): add delete_task_permanent service function"
```

---

### Task 1: Backend — endpoint `DELETE /api/image/task/{task_id}/permanent`

**Goal:** Пробросить `delete_task_permanent` наружу через HTTP. Зеркало endpoint-а Converter.

**Files:**
- Modify: `backend/app/routers/image.py` (добавить обработчик после `restore_task` на строке 625)

**Acceptance Criteria:**
- [ ] `DELETE /api/image/task/{task_id}/permanent` возвращает `{"detail": "ok"}` при успехе
- [ ] 404 «Задача не найдена или ещё активна» при неудаче (чужая, не существует, не-terminal)
- [ ] 403 если у юзера нет permission `image`
- [ ] Пишется audit-log `image_delete_permanent`
- [ ] Backend тесты не ломаются

**Verify:** `cd backend && pytest tests/ -v` → all green; ручная проверка через `curl` или Swagger UI

**Steps:**

- [ ] **Step 1: Добавить endpoint**

В `backend/app/routers/image.py`, после функции `restore_task` (которая заканчивается около строки 625), добавить:

```python
@router.delete("/task/{task_id}/permanent", response_model=dict)
async def delete_task_permanent(
    task_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Permanently delete an image task — removes file from disk and DB record.

    Only works for terminal tasks (ready/error).
    """
    _require_image_permission(user)

    deleted = await image_service.delete_task_permanent(
        task_id=task_id, user_id=user.id, db=db,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена или ещё активна",
        )

    await _log_audit(
        db=db,
        user_id=user.id,
        action="image_delete_permanent",
        details={"task_id": task_id},
        request=request,
    )
    await db.commit()

    logger.info("Image task %s permanently deleted by user %d", task_id, user.id)
    return {"detail": "ok"}
```

- [ ] **Step 2: Проверить, что приложение стартует**

Run: `cd backend && python -c "from app.main import app; print([r.path for r in app.routes if 'permanent' in r.path])"`
Expected: вывод содержит `/api/image/task/{task_id}/permanent`

- [ ] **Step 3: Прогнать все тесты**

Run: `cd backend && pytest tests/ -v`
Expected: all PASSED

- [ ] **Step 4: Коммит**

```bash
git add backend/app/routers/image.py
git commit -m "feat(image): add DELETE /task/{id}/permanent endpoint"
```

---

### Task 2: Frontend — настройка Vitest

**Goal:** Поднять unit-тесты во фронте. Vitest + @testing-library/react + jsdom. Один smoke-тест чтобы убедиться что всё работает.

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/vite.config.ts`
- Modify: `frontend/tsconfig.json`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/src/test/smoke.test.tsx` (удаляется после проверки)

**Acceptance Criteria:**
- [ ] `bun install` (или `npm install`) ставит новые пакеты без конфликтов
- [ ] `bun run test:run` проходит smoke-тест
- [ ] `bun run build` по-прежнему собирает фронт (не сломали tsconfig)
- [ ] `IntersectionObserver` stubbed globally в `setup.ts`

**Verify:** `cd frontend && bun run test:run` → 1 PASSED; `bun run build` → PASSED

**Steps:**

- [ ] **Step 1: Обновить `frontend/package.json`**

Добавить в `devDependencies`:

```json
"vitest": "^2.1.0",
"@testing-library/react": "^16.1.0",
"@testing-library/jest-dom": "^6.6.3",
"@testing-library/user-event": "^14.5.2",
"jsdom": "^25.0.1"
```

Добавить в `scripts`:

```json
"test": "vitest",
"test:run": "vitest run"
```

Итоговый файл (фрагмент):

```json
{
  "name": "naturalsk-web",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "test": "vitest",
    "test:run": "vitest run"
  },
  "dependencies": { "...": "..." },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/react": "^16.1.0",
    "@testing-library/user-event": "^14.5.2",
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.4",
    "jsdom": "^25.0.1",
    "typescript": "^5.6.3",
    "vite": "^5.4.11",
    "vitest": "^2.1.0"
  }
}
```

- [ ] **Step 2: Расширить `frontend/vite.config.ts`**

Заменить файл целиком:

```typescript
/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            proxyRes.headers['access-control-expose-headers'] = 'content-disposition'
          })
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
  },
})
```

- [ ] **Step 3: Обновить `frontend/tsconfig.json`**

Добавить `types` в `compilerOptions`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": false,
    "noUnusedParameters": false,
    "noFallthroughCasesInSwitch": true,
    "forceConsistentCasingInFileNames": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src"]
}
```

- [ ] **Step 4: Создать `frontend/src/test/setup.ts`**

```typescript
import '@testing-library/jest-dom'

// jsdom не реализует IntersectionObserver, а Thumbnail его использует.
class MockIntersectionObserver implements IntersectionObserver {
  readonly root = null
  readonly rootMargin = ''
  readonly thresholds = []
  constructor(private callback: IntersectionObserverCallback) {}
  observe(target: Element): void {
    // Имитируем мгновенное попадание в viewport — упрощает тесты,
    // которые проверяют реакцию на visibility.
    queueMicrotask(() => {
      this.callback(
        [
          {
            isIntersecting: true,
            target,
            intersectionRatio: 1,
            time: 0,
            boundingClientRect: {} as DOMRectReadOnly,
            intersectionRect: {} as DOMRectReadOnly,
            rootBounds: null,
          },
        ],
        this,
      )
    })
  }
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): IntersectionObserverEntry[] { return [] }
}

;(globalThis as unknown as { IntersectionObserver: unknown }).IntersectionObserver = MockIntersectionObserver

// URL.createObjectURL / revokeObjectURL в jsdom — стаб с предсказуемыми значениями
if (typeof URL.createObjectURL !== 'function') {
  let counter = 0
  // @ts-expect-error — jsdom позволяет переопределить
  URL.createObjectURL = () => `blob:mock-${counter++}`
  // @ts-expect-error
  URL.revokeObjectURL = () => {}
}
```

- [ ] **Step 5: Добавить smoke-тест**

Create `frontend/src/test/smoke.test.tsx`:

```typescript
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'

describe('Vitest setup', () => {
  it('renders a component and matches jest-dom', () => {
    render(<div>hello world</div>)
    expect(screen.getByText('hello world')).toBeInTheDocument()
  })

  it('has IntersectionObserver stubbed', () => {
    expect(typeof IntersectionObserver).toBe('function')
  })
})
```

- [ ] **Step 6: Установить пакеты и прогнать тесты**

Run: `cd frontend && bun install`
Expected: install completes without errors.

Run: `cd frontend && bun run test:run`
Expected: 2 PASSED.

Run: `cd frontend && bun run build`
Expected: build succeeds (tsc + vite build).

- [ ] **Step 7: Удалить smoke-тест**

```bash
rm frontend/src/test/smoke.test.tsx
```

- [ ] **Step 8: Коммит**

```bash
git add frontend/package.json frontend/package-lock.json frontend/bun.lockb frontend/vite.config.ts frontend/tsconfig.json frontend/src/test/setup.ts 2>/dev/null
git commit -m "chore(frontend): set up Vitest + Testing Library"
```

> **Note**: может существовать `bun.lockb` ИЛИ `package-lock.json` — добавить тот, что обновился (один из двух).

---

### Task 3: Frontend — `imageApi.deleteTaskPermanent`

**Goal:** Добавить клиентский метод для нового бэкенд-endpoint-а.

**Files:**
- Modify: `frontend/src/pages/ImageProcessor/imageApi.ts:97-109` (рядом с `dismissTask`, `restoreTask`)

**Acceptance Criteria:**
- [ ] Новый метод `deleteTaskPermanent(taskId: string): Promise<void>` добавлен
- [ ] TypeScript compile проходит
- [ ] Существующие методы не тронуты

**Verify:** `cd frontend && bun run build` → PASSED

**Steps:**

- [ ] **Step 1: Добавить метод**

В `frontend/src/pages/ImageProcessor/imageApi.ts`, в объект `imageApi`, после метода `restoreTask` (строки 107-109), добавить:

```typescript
  deleteTaskPermanent(taskId: string): Promise<void> {
    return api.delete(`/image/task/${taskId}/permanent`).then(() => undefined)
  },
```

Итоговый фрагмент:

```typescript
  restoreTask(taskId: string): Promise<void> {
    return api.post(`/image/task/${taskId}/restore`).then(() => undefined)
  },

  deleteTaskPermanent(taskId: string): Promise<void> {
    return api.delete(`/image/task/${taskId}/permanent`).then(() => undefined)
  },

  getQuota(): Promise<ImageQuota> {
    return api
      .get<ImageQuota>('/image/quota')
      .then((r) => r.data)
  },
```

- [ ] **Step 2: Проверить сборку**

Run: `cd frontend && bun run build`
Expected: build succeeds.

- [ ] **Step 3: Коммит**

```bash
git add frontend/src/pages/ImageProcessor/imageApi.ts
git commit -m "feat(image-ui): add deleteTaskPermanent API client method"
```

---

### Task 4: Frontend — компонент `Thumbnail` + тесты

**Goal:** Ленивая thumbnail-миниатюра с IntersectionObserver и корректным lifecycle-ом blob URL.

**Files:**
- Create: `frontend/src/pages/ImageProcessor/components/Thumbnail.tsx`
- Create: `frontend/src/pages/ImageProcessor/components/Thumbnail.module.css`
- Create: `frontend/src/pages/ImageProcessor/components/Thumbnail.test.tsx`

**Acceptance Criteria:**
- [ ] `Thumbnail` принимает `taskId`, `status`, `fileExists`, `operation`
- [ ] Запрос preview запускается только при попадании в viewport (через IntersectionObserver)
- [ ] При unmount — вызывается `URL.revokeObjectURL` для загруженного URL
- [ ] При 404 или network error показывается fallback — иконка операции
- [ ] Unit-тесты проходят

**Verify:** `cd frontend && bun run test:run src/pages/ImageProcessor/components/Thumbnail.test.tsx` → все PASSED

**Steps:**

- [ ] **Step 1: Написать тесты**

Create `frontend/src/pages/ImageProcessor/components/Thumbnail.test.tsx`:

```typescript
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import Thumbnail from './Thumbnail'

// Мокаем imageApi чтобы избежать реальных HTTP-вызовов
vi.mock('../imageApi', () => ({
  imageApi: {
    getPreview: vi.fn(),
    getResultPreview: vi.fn(),
  },
}))

import { imageApi } from '../imageApi'

describe('Thumbnail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('показывает fallback-иконку до загрузки preview', async () => {
    vi.mocked(imageApi.getPreview).mockResolvedValue('blob:mock-1')
    render(
      <Thumbnail
        taskId="task-1"
        status="pending"
        fileExists={false}
        operation="remove_bg"
      />,
    )
    // Икона операции видна как fallback
    expect(screen.getByTestId('thumbnail-fallback')).toBeInTheDocument()
  })

  it('использует getResultPreview при status=ready', async () => {
    vi.mocked(imageApi.getResultPreview).mockResolvedValue('blob:mock-result')
    render(
      <Thumbnail
        taskId="task-ready"
        status="ready"
        fileExists={true}
        operation="remove_bg"
      />,
    )
    await waitFor(() => {
      expect(imageApi.getResultPreview).toHaveBeenCalledWith('task-ready')
    })
  })

  it('использует getPreview при status=processing', async () => {
    vi.mocked(imageApi.getPreview).mockResolvedValue('blob:mock-input')
    render(
      <Thumbnail
        taskId="task-proc"
        status="processing"
        fileExists={false}
        operation="remove_watermark"
      />,
    )
    await waitFor(() => {
      expect(imageApi.getPreview).toHaveBeenCalledWith('task-proc')
    })
  })

  it('освобождает blob URL при unmount', async () => {
    vi.mocked(imageApi.getResultPreview).mockResolvedValue('blob:mock-cleanup')
    const revokeSpy = vi.spyOn(URL, 'revokeObjectURL')
    const { unmount } = render(
      <Thumbnail
        taskId="task-cleanup"
        status="ready"
        fileExists={true}
        operation="remove_bg"
      />,
    )
    await waitFor(() => {
      expect(imageApi.getResultPreview).toHaveBeenCalled()
    })
    unmount()
    expect(revokeSpy).toHaveBeenCalledWith('blob:mock-cleanup')
  })

  it('показывает fallback при ошибке загрузки', async () => {
    vi.mocked(imageApi.getResultPreview).mockRejectedValue(new Error('404'))
    render(
      <Thumbnail
        taskId="task-gone"
        status="ready"
        fileExists={false}
        operation="remove_bg"
      />,
    )
    await waitFor(() => {
      expect(screen.getByTestId('thumbnail-fallback')).toBeInTheDocument()
    })
  })
})
```

- [ ] **Step 2: Запустить тесты — убедиться что падают**

Run: `cd frontend && bun run test:run src/pages/ImageProcessor/components/Thumbnail.test.tsx`
Expected: FAIL — `Thumbnail` не существует.

- [ ] **Step 3: Создать `Thumbnail.module.css`**

```css
.container {
  width: 56px;
  height: 56px;
  flex-shrink: 0;
  border-radius: 6px;
  background: #f1f5f9;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #64748b;
}

.image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
}
```

- [ ] **Step 4: Создать `Thumbnail.tsx`**

```typescript
import { useEffect, useRef, useState } from 'react'
import { Wand2, Droplets } from 'lucide-react'
import { imageApi } from '../imageApi'
import type { ImageOperation, ImageStatus } from '../types'
import styles from './Thumbnail.module.css'

interface ThumbnailProps {
  taskId: string
  status: ImageStatus
  fileExists: boolean
  operation: ImageOperation
}

export default function Thumbnail({ taskId, status, fileExists, operation }: ThumbnailProps) {
  const [url, setUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const [visible, setVisible] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // Lazy-mount: запускаем fetch только когда контейнер виден в viewport
  useEffect(() => {
    if (!ref.current) return
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          setVisible(true)
          observer.disconnect()
          break
        }
      }
    })
    observer.observe(ref.current)
    return () => observer.disconnect()
  }, [])

  // Загрузка preview, когда карточка видима
  useEffect(() => {
    if (!visible) return
    const controller = new AbortController()
    let cancelled = false

    const loader = status === 'ready' && fileExists
      ? imageApi.getResultPreview
      : imageApi.getPreview

    loader(taskId)
      .then((blobUrl) => {
        if (cancelled) {
          URL.revokeObjectURL(blobUrl)
          return
        }
        setUrl(blobUrl)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [visible, taskId, status, fileExists])

  // Освобождаем blob URL при unmount или смене url
  useEffect(() => {
    return () => {
      if (url) URL.revokeObjectURL(url)
    }
  }, [url])

  if (url && !failed) {
    return (
      <div className={styles.container} ref={ref}>
        <img src={url} alt="" className={styles.image} />
      </div>
    )
  }

  const Icon = operation === 'remove_bg' ? Wand2 : Droplets
  return (
    <div className={styles.container} ref={ref}>
      <span className={styles.fallback} data-testid="thumbnail-fallback">
        <Icon size={24} aria-hidden="true" />
      </span>
    </div>
  )
}
```

- [ ] **Step 5: Запустить тесты — должны пройти**

Run: `cd frontend && bun run test:run src/pages/ImageProcessor/components/Thumbnail.test.tsx`
Expected: 5 PASSED.

- [ ] **Step 6: Коммит**

```bash
git add frontend/src/pages/ImageProcessor/components/Thumbnail.tsx frontend/src/pages/ImageProcessor/components/Thumbnail.module.css frontend/src/pages/ImageProcessor/components/Thumbnail.test.tsx
git commit -m "feat(image-ui): add lazy-loaded Thumbnail component"
```

---

### Task 5: Frontend — компонент `ImageProgress` + тесты

**Goal:** Карточка задачи (аналог `ConvertProgress`), реюзается для активных задач и истории.

**Files:**
- Create: `frontend/src/pages/ImageProcessor/components/ImageProgress.tsx`
- Create: `frontend/src/pages/ImageProcessor/components/ImageProgress.module.css`
- Create: `frontend/src/pages/ImageProcessor/components/ImageProgress.test.tsx`

**Acceptance Criteria:**
- [ ] Компонент рендерит thumbnail + имя + бейдж статуса + иконку операции + дату
- [ ] Прогресс-бар виден только при `status === 'processing'`
- [ ] Набор кнопок соответствует таблице спеки `(status, isHistory)`
- [ ] Обработчики `onDismiss`, `onRestore`, `onDownload`, `onDelete` вызываются с `task_id`
- [ ] Кнопка «Скачать» скрыта при `!file_exists`
- [ ] Unit-тесты проходят

**Verify:** `cd frontend && bun run test:run src/pages/ImageProcessor/components/ImageProgress.test.tsx` → все PASSED

**Steps:**

- [ ] **Step 1: Написать тесты**

Create `frontend/src/pages/ImageProcessor/components/ImageProgress.test.tsx`:

```typescript
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import ImageProgress from './ImageProgress'
import type { ImageTaskListItem } from '../types'

// Замокаем Thumbnail — не хотим сетевых вызовов в тестах ImageProgress
vi.mock('./Thumbnail', () => ({
  default: () => <div data-testid="thumbnail" />,
}))

function makeTask(overrides: Partial<ImageTaskListItem> = {}): ImageTaskListItem {
  return {
    task_id: 'task-1',
    status: 'ready',
    progress: 100,
    operation: 'remove_bg',
    filename: 'result.png',
    file_size: 1024,
    error: null,
    original_filename: 'input.jpg',
    original_ext: 'jpg',
    inpaint_method: null,
    created_at: '2026-04-21T10:00:00',
    completed_at: '2026-04-21T10:00:05',
    file_exists: true,
    ...overrides,
  }
}

describe('ImageProgress', () => {
  it('показывает имя файла и thumbnail', () => {
    render(
      <ImageProgress
        task={makeTask()}
        onDismiss={vi.fn()}
        onRestore={vi.fn()}
        onDownload={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    expect(screen.getByText('input.jpg')).toBeInTheDocument()
    expect(screen.getByTestId('thumbnail')).toBeInTheDocument()
  })

  it('при ready + !isHistory показывает Скачать / Скрыть / Удалить', () => {
    render(
      <ImageProgress
        task={makeTask({ status: 'ready' })}
        onDismiss={vi.fn()}
        onRestore={vi.fn()}
        onDownload={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: /скачать/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /скрыть/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /удалить/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /восстановить/i })).not.toBeInTheDocument()
  })

  it('при ready + isHistory показывает Скачать / Восстановить / Удалить', () => {
    render(
      <ImageProgress
        task={makeTask({ status: 'ready' })}
        isHistory
        onDismiss={vi.fn()}
        onRestore={vi.fn()}
        onDownload={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: /скачать/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /восстановить/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /удалить/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /скрыть/i })).not.toBeInTheDocument()
  })

  it('при processing не показывает никаких кнопок действий', () => {
    render(
      <ImageProgress
        task={makeTask({ status: 'processing', progress: 42 })}
        onDismiss={vi.fn()}
        onRestore={vi.fn()}
        onDownload={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    expect(screen.queryByRole('button', { name: /скачать/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /скрыть/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /удалить/i })).not.toBeInTheDocument()
  })

  it('показывает прогресс-бар при processing', () => {
    render(
      <ImageProgress
        task={makeTask({ status: 'processing', progress: 42 })}
        onDismiss={vi.fn()}
        onRestore={vi.fn()}
        onDownload={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
  })

  it('при error + !isHistory показывает Скрыть / Удалить, но не Скачать', () => {
    render(
      <ImageProgress
        task={makeTask({ status: 'error', error: 'boom' })}
        onDismiss={vi.fn()}
        onRestore={vi.fn()}
        onDownload={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    expect(screen.queryByRole('button', { name: /скачать/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /скрыть/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /удалить/i })).toBeInTheDocument()
  })

  it('Скачать отсутствует если file_exists=false', () => {
    render(
      <ImageProgress
        task={makeTask({ status: 'ready', file_exists: false })}
        onDismiss={vi.fn()}
        onRestore={vi.fn()}
        onDownload={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    expect(screen.queryByRole('button', { name: /скачать/i })).not.toBeInTheDocument()
  })

  it('onDownload получает task_id', () => {
    const onDownload = vi.fn()
    render(
      <ImageProgress
        task={makeTask({ task_id: 'abc' })}
        onDismiss={vi.fn()}
        onRestore={vi.fn()}
        onDownload={onDownload}
        onDelete={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /скачать/i }))
    expect(onDownload).toHaveBeenCalledWith('abc')
  })

  it('onDismiss получает task_id', () => {
    const onDismiss = vi.fn()
    render(
      <ImageProgress
        task={makeTask({ task_id: 'def' })}
        onDismiss={onDismiss}
        onRestore={vi.fn()}
        onDownload={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /скрыть/i }))
    expect(onDismiss).toHaveBeenCalledWith('def')
  })

  it('onRestore вызывается в режиме isHistory', () => {
    const onRestore = vi.fn()
    render(
      <ImageProgress
        task={makeTask({ task_id: 'hist-1' })}
        isHistory
        onDismiss={vi.fn()}
        onRestore={onRestore}
        onDownload={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /восстановить/i }))
    expect(onRestore).toHaveBeenCalledWith('hist-1')
  })
})
```

- [ ] **Step 2: Запустить тесты — ожидаем fail**

Run: `cd frontend && bun run test:run src/pages/ImageProcessor/components/ImageProgress.test.tsx`
Expected: FAIL — `ImageProgress` не существует.

- [ ] **Step 3: Создать `ImageProgress.module.css`**

```css
.card {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 10px 12px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  margin-bottom: 8px;
  transition: border-color 0.15s;
}
.card.history {
  background: #fafafa;
}
.card.ready { border-left: 3px solid #10b981; }
.card.error { border-left: 3px solid #ef4444; }

.info {
  flex: 1;
  min-width: 0;
}

.filename {
  font-weight: 500;
  font-size: 14px;
  color: #0f172a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.meta {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 4px;
  font-size: 12px;
  color: #64748b;
}

.operationIcon {
  color: #6366f1;
  flex-shrink: 0;
}

.badge {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 500;
}
.badgeReady { background: #d1fae5; color: #065f46; }
.badgeError { background: #fee2e2; color: #991b1b; }
.badgeProcessing { background: #dbeafe; color: #1e40af; }
.badgePending { background: #f1f5f9; color: #475569; }

.timestamp {
  font-size: 11px;
}

.progressWrap {
  width: 100%;
  height: 4px;
  background: #e5e7eb;
  border-radius: 2px;
  overflow: hidden;
  margin-top: 6px;
}

.progressFill {
  height: 100%;
  background: #3b82f6;
  transition: width 0.3s;
}

.actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  font-size: 12px;
  border: 1px solid #e5e7eb;
  background: #fff;
  border-radius: 6px;
  cursor: pointer;
  color: #0f172a;
  transition: background 0.15s, border-color 0.15s;
}
.btn:hover:not(:disabled) {
  background: #f8fafc;
  border-color: #cbd5e1;
}
.btn:disabled {
  opacity: 0.5;
  cursor: default;
}

.btnPrimary {
  background: #10b981;
  border-color: #10b981;
  color: #fff;
}
.btnPrimary:hover:not(:disabled) {
  background: #059669;
  border-color: #059669;
}

.btnDanger {
  color: #b91c1c;
  border-color: #fecaca;
}
.btnDanger:hover:not(:disabled) {
  background: #fef2f2;
}
```

- [ ] **Step 4: Создать `ImageProgress.tsx`**

```typescript
import { Wand2, Droplets, Download, RotateCcw, Trash2, X } from 'lucide-react'
import type { ImageTaskListItem, ImageStatus } from '../types'
import Thumbnail from './Thumbnail'
import styles from './ImageProgress.module.css'

const STATUS_LABELS: Record<ImageStatus, string> = {
  pending: 'Ожидание',
  uploading: 'Загрузка',
  processing: 'Обработка',
  ready: 'Готово',
  error: 'Ошибка',
}

function formatTimestamp(iso: string | null): string {
  if (!iso) return ''
  try {
    const normalized = /Z$|[+-]\d{2}:\d{2}$/.test(iso) ? iso : iso + 'Z'
    const d = new Date(normalized)
    return d.toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return ''
  }
}

interface ImageProgressProps {
  task: ImageTaskListItem
  isHistory?: boolean
  onDismiss: (taskId: string) => void
  onRestore: (taskId: string) => void
  onDownload: (taskId: string) => void
  onDelete: (taskId: string) => void
  downloadingId?: string | null
  restoringId?: string | null
  deletingId?: string | null
}

export default function ImageProgress({
  task,
  isHistory = false,
  onDismiss,
  onRestore,
  onDownload,
  onDelete,
  downloadingId,
  restoringId,
  deletingId,
}: ImageProgressProps) {
  const isReady = task.status === 'ready'
  const isError = task.status === 'error'
  const isProcessing = task.status === 'processing' || task.status === 'uploading'
  const isTerminal = isReady || isError
  const canDownload = isReady && task.file_exists

  const OperationIcon = task.operation === 'remove_bg' ? Wand2 : Droplets

  const badgeClass = (() => {
    switch (task.status) {
      case 'ready':      return styles.badgeReady
      case 'error':      return styles.badgeError
      case 'processing': return styles.badgeProcessing
      case 'uploading':  return styles.badgeProcessing
      default:           return styles.badgePending
    }
  })()

  const cardClass = [
    styles.card,
    isHistory ? styles.history : '',
    isReady ? styles.ready : '',
    isError ? styles.error : '',
  ].filter(Boolean).join(' ')

  return (
    <div
      className={cardClass}
      role="region"
      aria-label={`Задача ${task.original_filename}`}
    >
      <Thumbnail
        taskId={task.task_id}
        status={task.status}
        fileExists={task.file_exists}
        operation={task.operation}
      />

      <div className={styles.info}>
        <div className={styles.filename} title={task.original_filename}>
          {task.original_filename}
        </div>
        <div className={styles.meta}>
          <OperationIcon size={14} className={styles.operationIcon} aria-hidden="true" />
          <span className={`${styles.badge} ${badgeClass}`}>
            {STATUS_LABELS[task.status]}
          </span>
          <span className={styles.timestamp}>
            {formatTimestamp(task.completed_at ?? task.created_at)}
          </span>
        </div>
        {isProcessing && (
          <div
            className={styles.progressWrap}
            role="progressbar"
            aria-valuenow={task.progress}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div className={styles.progressFill} style={{ width: `${task.progress}%` }} />
          </div>
        )}
      </div>

      <div className={styles.actions}>
        {canDownload && (
          <button
            type="button"
            className={`${styles.btn} ${styles.btnPrimary}`}
            onClick={() => onDownload(task.task_id)}
            disabled={downloadingId === task.task_id}
            aria-busy={downloadingId === task.task_id}
          >
            <Download size={13} aria-hidden="true" />
            Скачать
          </button>
        )}

        {isTerminal && !isHistory && (
          <button
            type="button"
            className={styles.btn}
            onClick={() => onDismiss(task.task_id)}
            aria-label="Скрыть задачу в историю"
          >
            <X size={13} aria-hidden="true" />
            Скрыть
          </button>
        )}

        {isTerminal && isHistory && (
          <button
            type="button"
            className={styles.btn}
            onClick={() => onRestore(task.task_id)}
            disabled={restoringId === task.task_id}
            aria-busy={restoringId === task.task_id}
            aria-label="Восстановить задачу"
          >
            <RotateCcw size={13} aria-hidden="true" />
            Восстановить
          </button>
        )}

        {isTerminal && (
          <button
            type="button"
            className={`${styles.btn} ${styles.btnDanger}`}
            onClick={() => onDelete(task.task_id)}
            disabled={deletingId === task.task_id}
            aria-busy={deletingId === task.task_id}
            aria-label="Удалить задачу навсегда"
          >
            <Trash2 size={13} aria-hidden="true" />
            Удалить
          </button>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Прогнать тесты**

Run: `cd frontend && bun run test:run src/pages/ImageProcessor/components/ImageProgress.test.tsx`
Expected: 10 PASSED.

- [ ] **Step 6: Проверить сборку**

Run: `cd frontend && bun run build`
Expected: build succeeds.

- [ ] **Step 7: Коммит**

```bash
git add frontend/src/pages/ImageProcessor/components/ImageProgress.tsx frontend/src/pages/ImageProcessor/components/ImageProgress.module.css frontend/src/pages/ImageProcessor/components/ImageProgress.test.tsx
git commit -m "feat(image-ui): add ImageProgress task card component"
```

---

### Task 6: Frontend — полный рефактор `ImageProcessorPage` + редакторы

**Goal:** Перенести управление состоянием задач, polling и действия на уровень `ImageProcessorPage`. Рефактор `BackgroundRemoval` и `WatermarkRemoval` под новые props. Удаление `TaskHistory`. Интеграция `ImageProgress`.

**Files:**
- Modify: `frontend/src/pages/ImageProcessor/ImageProcessorPage.tsx` (полная замена)
- Modify: `frontend/src/pages/ImageProcessor/ImageProcessorPage.module.css` (добавить стили `tasksSection`, `historySection` — копия стиля из `ConverterPage.module.css`)
- Modify: `frontend/src/pages/ImageProcessor/components/BackgroundRemoval.tsx`
- Modify: `frontend/src/pages/ImageProcessor/components/WatermarkRemoval.tsx`
- Delete: `frontend/src/pages/ImageProcessor/components/TaskHistory.tsx`
- Delete: `frontend/src/pages/ImageProcessor/components/TaskHistory.module.css`

**Acceptance Criteria:**
- [ ] `ImageProcessorPage` держит `tasks: ImageTaskListItem[]`, `historyTasks: ImageTaskListItem[]`, `pollRefs`, `currentTaskIds: { bg, watermark }`
- [ ] На mount — `getTasks()`, `getHistory()`, `getQuota()`; polling возобновляется для `processing`-задач
- [ ] `BackgroundRemoval` и `WatermarkRemoval` больше не держат локального polling — принимают `currentTask`, `onProcessStart`, `onReset`, `onQuotaChange`
- [ ] Dismiss / dismiss-all / restore / permanent-delete работают через UI
- [ ] Resume-after-reload работает: запустить обработку → reload → карточка в «Активных» → при `ready` появляется toast
- [ ] `TaskHistory.tsx` / `.module.css` удалены, ни один файл не ссылается на них
- [ ] `bun run build` + `bun run test:run` проходят

**Verify:** `cd frontend && bun run test:run && bun run build` → всё зелено. Ручная проверка сценариев ниже.

**Steps:**

- [ ] **Step 1: Добавить стили секций в `ImageProcessorPage.module.css`**

Open `frontend/src/pages/ImageProcessor/ImageProcessorPage.module.css` и добавить в конец файла:

```css
.tasksSection,
.historySection {
  margin-top: 24px;
}

.sectionHeader {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.sectionTitle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}

.countBadge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border-radius: 999px;
  background: #e2e8f0;
  color: #475569;
  font-size: 11px;
  font-weight: 600;
}

.clearCompletedBtn {
  padding: 6px 12px;
  font-size: 12px;
  border: 1px solid #e5e7eb;
  background: #fff;
  border-radius: 6px;
  color: #64748b;
  cursor: pointer;
}
.clearCompletedBtn:hover {
  background: #f8fafc;
}

.historyToggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  font-size: 13px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  cursor: pointer;
  color: #334155;
}
.historyToggle:hover {
  background: #f8fafc;
}

.taskList,
.historyList {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
```

- [ ] **Step 2: Рефактор `BackgroundRemoval.tsx`**

Заменить файл целиком:

```typescript
import { useState, useEffect, useCallback } from 'react'
import { Download, RotateCcw, Loader2, Wand2 } from 'lucide-react'
import { toast } from 'react-toastify'

import { imageApi } from '../imageApi'
import type { ImageTaskListItem, ImageUploadResponse } from '../types'
import { ImageUploader } from './ImageUploader'
import { ImageCompare } from './ImageCompare'
import styles from './BackgroundRemoval.module.css'

type LocalPhase = 'idle' | 'uploading' | 'preview' | 'error'

interface BackgroundRemovalProps {
  currentTask: ImageTaskListItem | null
  onProcessStart: (task: ImageTaskListItem) => void
  onReset: () => void
  onQuotaChange?: () => void
}

export default function BackgroundRemoval({
  currentTask,
  onProcessStart,
  onReset,
  onQuotaChange,
}: BackgroundRemovalProps) {
  const [localPhase, setLocalPhase] = useState<LocalPhase>('idle')
  const [taskId, setTaskId] = useState<string | null>(null)
  const [previewUrl, setPreviewUrl] = useState('')
  const [resultPreviewUrl, setResultPreviewUrl] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [originalFilename, setOriginalFilename] = useState('')

  // Статус из внешнего источника (список задач в родителе)
  const processing = currentTask?.status === 'processing' || currentTask?.status === 'uploading'
  const ready = currentTask?.status === 'ready'
  const errored = currentTask?.status === 'error'

  // Отображаемая фаза: если есть currentTask — управляет она, иначе локальная
  const phase: 'idle' | 'preview' | 'processing' | 'result' | 'error' = processing
    ? 'processing'
    : ready
      ? 'result'
      : errored
        ? 'error'
        : localPhase

  // Revoke blob URLs on unmount
  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl)
      if (resultPreviewUrl) URL.revokeObjectURL(resultPreviewUrl)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Когда задача становится ready — подтягиваем result-preview для ImageCompare
  useEffect(() => {
    if (ready && currentTask && !resultPreviewUrl) {
      imageApi.getResultPreview(currentTask.task_id)
        .then(setResultPreviewUrl)
        .catch(() => undefined)
    }
  }, [ready, currentTask, resultPreviewUrl])

  // Когда задача становится error — показываем сообщение
  useEffect(() => {
    if (errored && currentTask?.error) {
      setError(currentTask.error)
    }
  }, [errored, currentTask])

  const handleUploaded = useCallback(async (response: ImageUploadResponse) => {
    setTaskId(response.task_id)
    setOriginalFilename(response.original_filename)
    try {
      const url = await imageApi.getPreview(response.task_id)
      setPreviewUrl(url)
      setLocalPhase('preview')
    } catch {
      setError('Не удалось загрузить превью')
      setLocalPhase('error')
    }
  }, [])

  const handleRemoveBg = useCallback(async () => {
    if (!taskId) return
    try {
      const task = await imageApi.removeBg(taskId)
      // Передаём родителю — он добавит карточку и запустит polling
      onProcessStart({
        ...task,
        file_exists: false,
      })
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Не удалось запустить обработку'
      setError(message)
      setLocalPhase('error')
    }
  }, [taskId, onProcessStart])

  const handleDownload = useCallback(async () => {
    if (!currentTask) return
    try {
      const { blob } = await imageApi.downloadResult(currentTask.task_id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const baseName = currentTask.original_filename.replace(/\.[^.]+$/, '')
      a.download = `${baseName}_no_bg.png`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch {
      toast.error('Не удалось скачать результат.')
    }
  }, [currentTask])

  const handleReset = useCallback(() => {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    if (resultPreviewUrl) URL.revokeObjectURL(resultPreviewUrl)
    setLocalPhase('idle')
    setTaskId(null)
    setPreviewUrl('')
    setResultPreviewUrl('')
    setError(null)
    setOriginalFilename('')
    onReset()
  }, [previewUrl, resultPreviewUrl, onReset])

  // Когда родитель сбрасывает currentTask извне (permanent-delete, dismiss из списка) —
  // синхронизируем локальное состояние
  useEffect(() => {
    if (currentTask === null && (localPhase === 'preview' || localPhase === 'error')) {
      // Уже отдыхаем в idle или ещё в работе — ничего не делаем
    }
  }, [currentTask, localPhase])

  // ── Render ──

  return (
    <div className={styles.container}>
      {phase === 'idle' && (
        <ImageUploader operation="remove_bg" onUploaded={handleUploaded} />
      )}

      {phase === 'preview' && (
        <div className={styles.previewSection}>
          <img src={previewUrl} alt="Превью" className={styles.previewImage} />
          <div className={styles.resultActions}>
            <button className={styles.primaryBtn} onClick={handleRemoveBg}>
              <Wand2 size={16} aria-hidden="true" />
              Удалить фон
            </button>
            <button className={styles.secondaryBtn} onClick={handleReset}>
              <RotateCcw size={16} aria-hidden="true" />
              Загрузить другое
            </button>
          </div>
        </div>
      )}

      {phase === 'processing' && (
        <div className={styles.processingSection}>
          <Loader2 size={32} className={styles.iconSpin} aria-hidden="true" />
          <p className={styles.processingText}>
            Обработка... {currentTask?.progress ?? 0}%
          </p>
          <div className={styles.progressBarWrap}>
            <div
              className={styles.progressBarFill}
              style={{ width: `${currentTask?.progress ?? 0}%` }}
            />
          </div>
        </div>
      )}

      {phase === 'result' && currentTask && (
        <div className={styles.resultSection}>
          <ImageCompare
            beforeSrc={previewUrl}
            afterSrc={resultPreviewUrl}
            transparencyGrid
          />
          <div className={styles.resultActions}>
            <button
              className={styles.successBtn}
              onClick={handleDownload}
              disabled={!currentTask.file_exists}
            >
              <Download size={16} aria-hidden="true" />
              Скачать PNG
            </button>
            <button className={styles.secondaryBtn} onClick={handleReset}>
              <RotateCcw size={16} aria-hidden="true" />
              Загрузить другое
            </button>
          </div>
        </div>
      )}

      {phase === 'error' && (
        <div className={styles.errorSection}>
          <p className={styles.errorMessage}>{error ?? currentTask?.error}</p>
          <button className={styles.secondaryBtn} onClick={handleReset}>
            <RotateCcw size={16} aria-hidden="true" />
            Попробовать снова
          </button>
        </div>
      )}

      {/* originalFilename используется где-то ещё? — держим в state для download-имени через currentTask */}
      {originalFilename && null}
    </div>
  )
}
```

- [ ] **Step 3: Рефактор `WatermarkRemoval.tsx`**

Прочитать текущий файл и заменить по той же схеме: убрать `pollRef`, `pollCountRef`, фазы `processing` / `result` из локального состояния; принять `currentTask`, `onProcessStart`, `onReset`, `onQuotaChange` через props. Логика редактирования маски (`shapes`, `tool`, `brushSize`, `inpaintMethod`, `imageNaturalSize`) остаётся локальной.

Ключевой блок — замена `handleProcess`:

```typescript
const handleProcess = useCallback(async () => {
  if (!taskId || shapes.length === 0) return
  try {
    const task = await imageApi.removeWatermark(
      taskId,
      shapes,
      inpaintMethod,
      imageNaturalSize.width,
    )
    onProcessStart({ ...task, file_exists: false })
  } catch (err: unknown) {
    const message =
      (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
      'Не удалось запустить обработку'
    setError(message)
    setLocalPhase('error')
  }
}, [taskId, shapes, inpaintMethod, imageNaturalSize.width, onProcessStart])
```

Остальной код Watermark-а адаптируется аналогично BackgroundRemoval: `phase` вычисляется из `currentTask`, локальный стейт хранит `LocalPhase = 'idle' | 'uploading' | 'editing' | 'error'`, блок `result` рендерится при `currentTask?.status === 'ready'`.

Поскольку Watermark-редактор большой, делаем полный рерайт по той же структуре, что BackgroundRemoval, — без дублирования кода маски здесь (она остаётся как в оригинале). Принцип: **локальные фазы до запуска обработки** (`'idle' | 'uploading' | 'editing' | 'error'`), **фазы после старта** (`'processing' | 'result' | 'error'`) — из `currentTask.status`.

- [ ] **Step 4: Рефактор `ImageProcessorPage.tsx`**

Заменить файл целиком:

```typescript
import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Image as ImageIcon,
  Wand2,
  Droplets,
  History,
  ChevronDown,
  ChevronUp,
  Clock,
} from 'lucide-react'
import { toast } from 'react-toastify'
import axios from 'axios'

import { imageApi } from './imageApi'
import type { ImageTaskListItem, ImageQuota } from './types'
import BackgroundRemoval from './components/BackgroundRemoval'
import WatermarkRemoval from './components/WatermarkRemoval'
import ImageProgress from './components/ImageProgress'
import styles from './ImageProcessorPage.module.css'

const POLL_INTERVAL = 2000
const TERMINAL_STATUSES = new Set<string>(['ready', 'error'])
const ACTIVE_STATUSES = new Set<string>(['pending', 'uploading', 'processing'])

type TabKey = 'bg' | 'watermark'

export default function ImageProcessorPage() {
  const [activeTab, setActiveTab] = useState<TabKey>('bg')

  const [tasks, setTasks] = useState<ImageTaskListItem[]>([])
  const [historyTasks, setHistoryTasks] = useState<ImageTaskListItem[]>([])
  const [quota, setQuota] = useState<ImageQuota | null>(null)
  const [showHistory, setShowHistory] = useState(false)

  const [currentTaskIds, setCurrentTaskIds] = useState<{ bg: string | null; watermark: string | null }>({
    bg: null,
    watermark: null,
  })

  const [downloadingId, setDownloadingId] = useState<string | null>(null)
  const [restoringId, setRestoringId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  // Polling — паттерн из ConverterPage.tsx:140-262
  const pollRefs = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map())
  const isPausedRef = useRef(false)

  // Cleanup всех интервалов при unmount
  useEffect(() => {
    return () => {
      pollRefs.current.forEach((id) => clearInterval(id))
    }
  }, [])

  // Пауза polling-а когда вкладка браузера скрыта
  useEffect(() => {
    function handle() {
      isPausedRef.current = document.hidden
    }
    document.addEventListener('visibilitychange', handle)
    return () => document.removeEventListener('visibilitychange', handle)
  }, [])

  const refreshQuota = useCallback(() => {
    imageApi.getQuota().then(setQuota).catch(() => undefined)
  }, [])

  const startPolling = useCallback((taskId: string) => {
    if (pollRefs.current.has(taskId)) return
    let consecutiveErrors = 0

    const intervalId = setInterval(async () => {
      if (isPausedRef.current) return
      try {
        const status = await imageApi.getStatus(taskId)
        consecutiveErrors = 0

        setTasks((prev) =>
          prev.map((t) =>
            t.task_id === taskId
              ? { ...t, ...status, file_exists: status.status === 'ready' ? true : t.file_exists }
              : t,
          ),
        )

        if (TERMINAL_STATUSES.has(status.status)) {
          clearInterval(intervalId)
          pollRefs.current.delete(taskId)
          if (status.status === 'ready') {
            toast.success(`Обработка завершена: ${status.original_filename}`)
            refreshQuota()
          } else if (status.status === 'error') {
            toast.error(`Ошибка обработки: ${status.original_filename}`)
          }
        }
      } catch (err: unknown) {
        if (axios.isAxiosError(err) && (err.response?.status === 401 || err.response?.status === 403)) {
          clearInterval(intervalId)
          pollRefs.current.delete(taskId)
          return
        }
        consecutiveErrors += 1
        if (consecutiveErrors >= 3) {
          clearInterval(intervalId)
          pollRefs.current.delete(taskId)
          toast.error('Потеряна связь с сервером. Обновите страницу для проверки статуса обработки.')
        }
      }
    }, POLL_INTERVAL)

    pollRefs.current.set(taskId, intervalId)
  }, [refreshQuota])

  // Начальная загрузка
  useEffect(() => {
    imageApi.getTasks()
      .then((items) => {
        setTasks(items)
        items.forEach((t) => {
          if (ACTIVE_STATUSES.has(t.status)) startPolling(t.task_id)
        })
      })
      .catch(() => undefined)
    imageApi.getHistory().then(setHistoryTasks).catch(() => undefined)
    refreshQuota()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── Handlers ──

  const handleProcessStart = useCallback((task: ImageTaskListItem) => {
    setTasks((prev) => [task, ...prev])
    setCurrentTaskIds((prev) => ({ ...prev, [activeTab]: task.task_id }))
    startPolling(task.task_id)
  }, [activeTab, startPolling])

  const handleEditorReset = useCallback(() => {
    setCurrentTaskIds((prev) => ({ ...prev, [activeTab]: null }))
  }, [activeTab])

  const handleDismiss = useCallback((taskId: string) => {
    imageApi.dismissTask(taskId).catch(() => undefined)
    const interval = pollRefs.current.get(taskId)
    if (interval) {
      clearInterval(interval)
      pollRefs.current.delete(taskId)
    }
    setTasks((prev) => {
      const dismissed = prev.find((t) => t.task_id === taskId)
      if (dismissed) {
        queueMicrotask(() => {
          setHistoryTasks((h) => {
            if (h.some((i) => i.task_id === taskId)) return h
            return [dismissed, ...h]
          })
        })
      }
      return prev.filter((t) => t.task_id !== taskId)
    })
    setCurrentTaskIds((prev) => {
      const next = { ...prev }
      if (next.bg === taskId) next.bg = null
      if (next.watermark === taskId) next.watermark = null
      return next
    })
  }, [])

  const handleDismissCompleted = useCallback(async () => {
    try {
      await imageApi.dismissCompleted()
    } catch {
      // игнорируем — чистим UI всё равно
    }
    setTasks((prev) => {
      const terminal = prev.filter((t) => TERMINAL_STATUSES.has(t.status))
      if (terminal.length > 0) {
        queueMicrotask(() => {
          setHistoryTasks((h) => {
            const existing = new Set(h.map((i) => i.task_id))
            const deduped = terminal.filter((t) => !existing.has(t.task_id))
            return [...deduped, ...h]
          })
        })
      }
      return prev.filter((t) => !TERMINAL_STATUSES.has(t.status))
    })
    setCurrentTaskIds((prev) => {
      const next = { ...prev }
      const stillActive = new Set(
        tasks.filter((t) => !TERMINAL_STATUSES.has(t.status)).map((t) => t.task_id),
      )
      if (next.bg && !stillActive.has(next.bg)) next.bg = null
      if (next.watermark && !stillActive.has(next.watermark)) next.watermark = null
      return next
    })
  }, [tasks])

  const handleRestore = useCallback(async (taskId: string) => {
    setRestoringId(taskId)
    try {
      await imageApi.restoreTask(taskId)
      const restored = historyTasks.find((h) => h.task_id === taskId)
      if (restored) {
        setTasks((prev) => [restored, ...prev])
        setHistoryTasks((prev) => prev.filter((h) => h.task_id !== taskId))
      }
      toast.info('Задача восстановлена.')
    } catch {
      toast.error('Не удалось восстановить задачу.')
    } finally {
      setRestoringId(null)
    }
  }, [historyTasks])

  const handleDownload = useCallback(async (taskId: string) => {
    setDownloadingId(taskId)
    try {
      const { blob, filename } = await imageApi.downloadResult(taskId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch {
      toast.error('Не удалось скачать файл. Возможно, он уже удалён.')
    } finally {
      setDownloadingId(null)
    }
  }, [])

  const handlePermanentDelete = useCallback(async (taskId: string) => {
    setDeletingId(taskId)
    try {
      await imageApi.deleteTaskPermanent(taskId)
      setTasks((prev) => prev.filter((t) => t.task_id !== taskId))
      setHistoryTasks((prev) => prev.filter((h) => h.task_id !== taskId))
      setCurrentTaskIds((prev) => {
        const next = { ...prev }
        if (next.bg === taskId) next.bg = null
        if (next.watermark === taskId) next.watermark = null
        return next
      })
    } catch {
      toast.error('Не удалось удалить задачу.')
    } finally {
      setDeletingId(null)
    }
  }, [])

  // Derived

  const currentBgTask = tasks.find((t) => t.task_id === currentTaskIds.bg) ?? null
  const currentWmTask = tasks.find((t) => t.task_id === currentTaskIds.watermark) ?? null
  const hasCompleted = tasks.some((t) => TERMINAL_STATUSES.has(t.status))

  // Render

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div className={styles.pageTitleRow}>
          <h1 className={styles.pageTitle}>
            <ImageIcon size={24} aria-hidden="true" />
            Image Processor
          </h1>
          {quota && (
            <span className={styles.quotaBadge}>
              {quota.used} / {quota.limit} сегодня
            </span>
          )}
        </div>
      </div>

      <div className={styles.tabs}>
        <button
          className={activeTab === 'bg' ? styles.tabActive : styles.tab}
          onClick={() => setActiveTab('bg')}
        >
          <Wand2 size={16} aria-hidden="true" />
          Удаление фона
        </button>
        <button
          className={activeTab === 'watermark' ? styles.tabActive : styles.tab}
          onClick={() => setActiveTab('watermark')}
        >
          <Droplets size={16} aria-hidden="true" />
          Удаление водяных знаков
        </button>
      </div>

      <div className={styles.content}>
        {activeTab === 'bg' ? (
          <BackgroundRemoval
            currentTask={currentBgTask}
            onProcessStart={handleProcessStart}
            onReset={handleEditorReset}
            onQuotaChange={refreshQuota}
          />
        ) : (
          <WatermarkRemoval
            currentTask={currentWmTask}
            onProcessStart={handleProcessStart}
            onReset={handleEditorReset}
            onQuotaChange={refreshQuota}
          />
        )}
      </div>

      {tasks.length > 0 && (
        <div className={styles.tasksSection}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionTitle}>
              <Clock size={14} aria-hidden="true" />
              Активные задачи
              <span className={styles.countBadge}>{tasks.length}</span>
            </span>
            {hasCompleted && (
              <button
                type="button"
                className={styles.clearCompletedBtn}
                onClick={handleDismissCompleted}
                aria-label="Скрыть все завершённые задачи"
              >
                Скрыть завершённые
              </button>
            )}
          </div>
          <div className={styles.taskList} aria-live="polite">
            {tasks.map((task) => (
              <ImageProgress
                key={task.task_id}
                task={task}
                onDismiss={handleDismiss}
                onRestore={handleRestore}
                onDownload={handleDownload}
                onDelete={handlePermanentDelete}
                downloadingId={downloadingId}
                restoringId={restoringId}
                deletingId={deletingId}
              />
            ))}
          </div>
        </div>
      )}

      {historyTasks.length > 0 && (
        <div className={styles.historySection}>
          <button
            type="button"
            className={styles.historyToggle}
            onClick={() => setShowHistory((v) => !v)}
            aria-expanded={showHistory}
          >
            <History size={13} aria-hidden="true" />
            История обработки
            <span className={styles.countBadge}>{historyTasks.length}</span>
            {showHistory
              ? <ChevronUp size={13} aria-hidden="true" />
              : <ChevronDown size={13} aria-hidden="true" />
            }
          </button>

          {showHistory && (
            <div className={styles.historyList} aria-live="polite">
              {historyTasks.map((task) => (
                <ImageProgress
                  key={task.task_id}
                  task={task}
                  isHistory
                  onDismiss={handleDismiss}
                  onRestore={handleRestore}
                  onDownload={handleDownload}
                  onDelete={handlePermanentDelete}
                  downloadingId={downloadingId}
                  restoringId={restoringId}
                  deletingId={deletingId}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Удалить `TaskHistory`**

```bash
rm frontend/src/pages/ImageProcessor/components/TaskHistory.tsx
rm frontend/src/pages/ImageProcessor/components/TaskHistory.module.css
```

Проверить, что нет остаточных импортов:

Run: `cd frontend && grep -r "TaskHistory" src/ --include="*.tsx" --include="*.ts"`
Expected: пустой вывод.

- [ ] **Step 6: Проверить сборку и тесты**

Run: `cd frontend && bun run test:run`
Expected: все существующие тесты PASSED.

Run: `cd frontend && bun run build`
Expected: build succeeds.

- [ ] **Step 7: Ручная верификация**

Запустить бэкенд и фронт:

```bash
# Терминал 1
cd backend && uvicorn app.main:app --reload

# Терминал 2
cd frontend && bun run dev
```

Пройти сценарии:

1. Открыть `/image`, авторизованный под юзером с permission `image`.
2. Загрузить JPG → удалить фон → дождаться `ready`.
3. Увидеть карточку в «Активные задачи» (1), редактор показывает ImageCompare.
4. Кликнуть «Скрыть» на карточке → карточка уехала в «История обработки» (1), редактор сбросился на `idle`.
5. Развернуть «История» → кликнуть «Восстановить» → карточка обратно в «Активные».
6. Загрузить второе изображение, запустить обработку. После `ready` ещё карточка.
7. Кликнуть «Скрыть завершённые» → обе ready-карточки в истории одним кликом.
8. В истории кликнуть «Удалить» на одной → карточка исчезла; F5 браузера → она не вернулась.
9. Запустить новую обработку, во время `processing` перезагрузить F5 → карточка в «Активных» со статусом «Обработка NN%», polling возобновился, через ~10 сек статус → `ready`.
10. Переключиться на вкладку «Удаление водяных знаков», загрузить картинку, поставить маску, запустить. После `ready` карточка в общем списке.

Если любой сценарий сломан — исправить до коммита.

- [ ] **Step 8: Коммит**

```bash
git add frontend/src/pages/ImageProcessor/
git commit -m "feat(image-ui): page-level tasks list with history and polling

Полный рефактор Image Processor под модель File Converter:
- tasks[] и historyTasks[] живут в ImageProcessorPage
- page-level polling вместо локального в редакторах
- новый ImageProgress для карточек + Thumbnail lazy-load
- удалён старый TaskHistory
- support для dismiss / dismiss-all / restore / permanent-delete
- resume-after-reload через getTasks + автополлинг processing-задач"
```

---

## Self-Review

**Spec coverage check:**

| Spec section | Task |
|---|---|
| Backend: `DELETE /task/{id}/permanent` + `delete_task_permanent` | Task 0 + Task 1 |
| Frontend test infra (Vitest) | Task 2 |
| `imageApi.deleteTaskPermanent` | Task 3 |
| `Thumbnail` компонент с lazy-load | Task 4 |
| `ImageProgress` компонент | Task 5 |
| Page-level polling + списки + резюме-after-reload | Task 6 |
| Рефактор `BackgroundRemoval` и `WatermarkRemoval` | Task 6 |
| Удаление `TaskHistory` | Task 6 |
| Стили секций | Task 6 (Step 1) |
| Unit-тесты `ImageProgress` | Task 5 |
| Unit-тесты `Thumbnail` | Task 4 |
| Backend pytest `test_image_permanent_delete` | Task 0 |
| Ручная верификация | Task 6 Step 7 |

Всё покрыто.

**Type consistency check:**
- `ImageTaskListItem` используется единообразно во всех тасках — это `ImageTaskStatus` + `file_exists: boolean` (из `types.ts`).
- `onProcessStart`, `onReset`, `currentTask` — одинаковые сигнатуры в обоих редакторах (Task 6 Step 2 и Step 3).
- `handleDismiss` / `handleRestore` / `handleDownload` / `handlePermanentDelete` принимают `(taskId: string)`.

Все консистентны.

**Placeholder check:** нет — каждый step содержит либо полный код, либо точную команду с expected output.
