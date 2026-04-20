# Image Processor — история файлов в стиле File Converter

**Дата:** 2026-04-21
**Модуль:** Image Processor (`/frontend/src/pages/ImageProcessor`, `/backend/app/routers/image.py`)
**Связанные фичи:** File Converter history (`/frontend/src/pages/Converter`, `/backend/app/routers/convert.py`)

## Цель

Привести UX истории обработки изображений в соответствие с File Converter: полноценные секции «Активные задачи» и «История», карточки с thumbnail-превью, resume-after-reload, dismiss / restore / permanent-delete / bulk-hide, polling на уровне страницы.

Текущий `TaskHistory` заменяется новым `ImageProgress` — прямым аналогом `ConvertProgress`. Подход 1 из брейншторма: полное зеркало архитектуры Converter с небольшим рефактором дочерних редакторов.

## Scope и ключевые решения (из брейншторма)

| Вопрос | Решение |
|---|---|
| Scope переноса | Полный перенос модели Converter: активные задачи + история |
| Workflow в редакторе | Одна задача в редакторе за раз; завершённые накапливаются карточками |
| Что после `ready` | Результат остаётся в редакторе + дубликат-карточка в списке «Активные» |
| Клик по карточке | Только явные кнопки; клик по телу — ничего |
| Содержимое карточки | Thumbnail 56×56 + имя + бейдж + иконка операции + дата + кнопки |
| Набор действий | Полный паритет с Converter; permanent-delete без confirm-диалога |

## Архитектура

`ImageProcessorPage` становится держателем состояния списков, polling-а, квоты — по аналогии с `ConverterPage`.

```
ImageProcessorPage
├── <Header + quota>
├── <Tabs: bg | watermark>
├── <EditorArea>
│   └── BackgroundRemoval | WatermarkRemoval
│         props: currentTask: ImageTaskListItem | null,
│                onProcessStart(task), onReset()
├── <TasksSection>                   // активные задачи
│   └── ImageProgress  (isHistory=false)
└── <HistorySection>                 // сворачиваемая, как в Converter
    └── ImageProgress  (isHistory=true)
```

Сдвиг ответственности:

- Polling переезжает в `ImageProcessorPage`. Паттерн 1-в-1 из `ConverterPage.tsx:205-262`:
  `pollRefs: Map<taskId, intervalId>` + `isPausedRef` на `visibilitychange` + `consecutiveErrors` с отсечкой при 3.
- Редактор сохраняет mask/preview/upload-логику, но **больше не держит** локальных фаз `processing` / `result`. Статус читает из `props.currentTask.status`. ImageCompare рендерится, когда `status === 'ready'`; прогресс-бар — при `processing`.
- Карточки `ImageProgress` — презентационные; действия через callbacks к родителю.
- `activeTab` (bg | watermark) не влияет на список задач — список один, карточки различаются иконкой операции.

**`currentTask` — per-tab:**
Состояние «какая задача сейчас в редакторе» хранится как
```ts
const [currentTaskIds, setCurrentTaskIds] = useState<{ bg: string | null; watermark: string | null }>({ bg: null, watermark: null })
```
При переключении вкладок каждый редактор помнит свою задачу. Это позволяет параллельно видеть результат bg на одной вкладке и работать с watermark на другой.

## Компоненты

### Новые файлы

**`frontend/src/pages/ImageProcessor/components/ImageProgress.tsx`**

Карточка задачи. Структурно повторяет `ConvertProgress`, визуально адаптирована:

- **Слева:** thumbnail 56×56 (lazy через IntersectionObserver); fallback — иконка операции 32px на сером фоне.
- **Центр:** имя файла (truncate) + бейдж статуса + иконка операции (Wand2/Droplets) + относительная дата (`completed_at ?? created_at`).
- **Прогресс-бар:** под контентом при `status === 'processing'` (высота 4px, показывает `progress` %).
- **Справа — кнопки, зависят от `(status, isHistory)`:**

  | status | isHistory=false (активная) | isHistory=true (история) |
  |---|---|---|
  | `processing` | — (только прогресс) | — (N/A, в истории не должно быть processing) |
  | `ready` | Скачать, Скрыть в историю, Удалить навсегда | Скачать, Восстановить, Удалить навсегда |
  | `error` | Скрыть в историю, Удалить навсегда | Восстановить, Удалить навсегда |

  Кнопка «Скачать» скрывается, если `!file_exists` (файл протух).

**`frontend/src/pages/ImageProcessor/components/ImageProgress.module.css`**

Свои стили. Не переиспользуем CSS Converter — thumbnail ломает grid-раскладку `ConvertProgress`.

**`frontend/src/pages/ImageProcessor/components/Thumbnail.tsx`**

Обёртка над `imageApi.getPreview(taskId)` / `getResultPreview(taskId)`. Инкапсулирует:
- IntersectionObserver — fetch запускается при попадании карточки в viewport.
- `AbortController` на случай unmount во время in-flight запроса.
- `URL.revokeObjectURL` в `useEffect` cleanup.
- Fallback на иконку при 404 / network error.

Какой preview качать — по таблице:

| status | источник | fallback |
|---|---|---|
| `pending` / `processing` / `error` | `/preview/{task_id}` (input) | иконка |
| `ready` | `/preview-result/{task_id}` | `/preview/{task_id}` |

### Удаляемые файлы

- `frontend/src/pages/ImageProcessor/components/TaskHistory.tsx`
- `frontend/src/pages/ImageProcessor/components/TaskHistory.module.css`

Функциональность полностью покрывается `ImageProgress` + секцией `<HistorySection>` в `ImageProcessorPage`.

### Меняемые файлы

**`frontend/src/pages/ImageProcessor/ImageProcessorPage.tsx`** — полный рефактор. Добавляется:
- `tasks: ImageTaskListItem[]` + `historyTasks: ImageTaskListItem[]`
- `pollRefs`, `isPausedRef`, `startPolling(taskId)` — копия паттерна Converter
- `currentTaskIds: { bg, watermark }`
- Обработчики: `handleProcessStart`, `handleDismiss`, `handleDismissCompleted`, `handleRestore`, `handleDownload`, `handlePermanentDelete`, `handleEditorReset`
- `useEffect` при mount: `imageApi.getTasks()` + resume polling для `processing`-задач; `getHistory()`; `getQuota()`

**`frontend/src/pages/ImageProcessor/components/BackgroundRemoval.tsx`**

Props меняются:
```ts
interface BackgroundRemovalProps {
  currentTask: ImageTaskListItem | null
  onProcessStart: (task: ImageTaskListItem) => void
  onReset: () => void
  onQuotaChange?: () => void
}
```

Изменения:
- Убираем локальные состояния `phase: 'processing' | 'result'`, `progress`, `pollRef`, `pollCountRef`. (Оставляем `idle`, `preview`, `error` — это редакторные состояния до запуска.)
- После `imageApi.removeBg(taskId)` вызываем `onProcessStart(task)`. Родитель добавит карточку и запустит polling.
- Рендер: если `currentTask.status === 'processing'` — прогресс-бар (читает из `currentTask.progress`); если `'ready'` — ImageCompare; если `'error'` — сообщение.
- `handleReset` вызывает `onReset()` дополнительно к локальному сбросу.

**`frontend/src/pages/ImageProcessor/components/WatermarkRemoval.tsx`** — аналогичные изменения.

**`frontend/src/pages/ImageProcessor/imageApi.ts`** — добавляется:
```ts
deleteTaskPermanent(taskId: string): Promise<void> {
  return api.delete(`/image/task/${taskId}/permanent`).then(() => undefined)
}
```

**`frontend/src/pages/ImageProcessor/types.ts`** — без изменений.

## Поток данных

### Монтирование страницы
1. `GET /api/image/tasks` → `tasks[]`. Для элементов `status === 'processing'` — `startPolling(taskId)`.
2. `GET /api/image/tasks/history` → `historyTasks[]`.
3. `GET /api/image/quota` → `quota`.

### Upload → Edit → Process
1. Редактор: `POST /image/upload` → `task_id`.
2. Редактор показывает preview (bg) или preview + mask (watermark).
3. Юзер жмёт «Удалить фон» / «Удалить ВЗ»:
   - Редактор вызывает `imageApi.removeBg(...)` / `removeWatermark(...)` → backend запускает BackgroundTask.
   - Редактор вызывает `onProcessStart(task)`, передавая актуальный `ImageTaskListItem`.
   - Родитель: `setTasks([newTask, ...prev])`, `startPolling(taskId)`, `setCurrentTaskIds(prev => ({ ...prev, [activeTab]: taskId }))`.
4. Polling раз в 2 сек. На каждом tick обновляет задачу в `tasks[]` через setTasks-map.
5. При `ready`: `clearInterval`, `pollRefs.delete(taskId)`, toast-success, `imageApi.getQuota()`. Редактор по `currentTask.status === 'ready'` рендерит ImageCompare.
6. При `error`: `clearInterval`, toast-error. Редактор показывает ошибку.

### Dismiss → История
- `imageApi.dismissTask(taskId)` + оптимистично: через `queueMicrotask` переместить из `tasks` в `historyTasks` (dedupe по `task_id`).
- Если `taskId === currentTaskIds[someTab]` — `onReset()` для соответствующего редактора; сбросить `currentTaskIds[tab] = null`.

### Bulk «Скрыть завершённые»
- `imageApi.dismissCompleted()` → переместить все `ready` и `error` из `tasks` в `historyTasks` (dedupe).
- Сбросить `currentTaskIds` для тех вкладок, чьи current-задачи попали в историю.

### Restore
- `imageApi.restoreTask(taskId)` → переместить из `historyTasks` в `tasks`.
- Редактор **не трогаем** — юзер может быть в середине другой работы.

### Permanent delete
- `imageApi.deleteTaskPermanent(taskId)` без confirm-диалога.
- Удалить из обоих списков. Если это current-задача для какого-то таба — `onReset()` для него.

### Polling cleanup
- `useEffect` cleanup при unmount страницы: `pollRefs.forEach(id => clearInterval(id))`.

## Thumbnails — управление памятью и загрузкой

- **Ленивая загрузка:** IntersectionObserver внутри `Thumbnail`. Fetch только когда карточка попадает в viewport.
- **Не освобождаем при выходе из viewport** — при скролле обратно thumbnail уже в памяти (Blob остаётся, URL валиден).
- **Освобождаем при unmount:** `URL.revokeObjectURL(url)` в `useEffect` cleanup. AbortController отменяет in-flight запросы при unmount.
- **Fallback:** при 404 / network error показываем иконку операции (Wand2 / Droplets) 32px в контейнере 56×56 с серым фоном.
- **Ресурсы:** preview на backend уже 800px JPG (~20-80 KB). Для 50 карточек — ~1-4 MB total. Акцептабельно.

## Backend

### Новый эндпоинт: `DELETE /api/image/task/{task_id}/permanent`

Прямой аналог `DELETE /api/convert/task/{task_id}/permanent` (convert.py:681-704):
- Permission check (`_require_image_permission`).
- Ownership check (`image_service.get_task_for_user`) — 404 если чужая или не существует.
- `rmtree(uploads/{task_id}/)`.
- Очистить in-memory cache в `image_service` (удалить из `_tasks_cache`).
- Удалить строку `ImageTask` из БД.
- Audit log: `image_delete_permanent`.
- Response: `{"detail": "ok"}`.

Новая функция в `image_service.py`:
```python
async def delete_task_permanent(task_id: str, user_id: int, db: AsyncSession) -> bool:
    """Удалить задачу и файлы полностью. Возвращает True, если найдена и удалена."""
```

### Существующие эндпоинты — переиспользуем as-is

- `GET /api/image/tasks` — `get_user_tasks` в `image_service.py:813-827` уже не фильтрует по статусу (только по `user_id`, `hidden`, TTL-cutoff), поэтому `processing`-задачи попадают в ответ. Никаких правок не нужно.
- `/preview/{task_id}` и `/preview-result/{task_id}` — уже есть, используются для thumbnails.

### Что не трогаем

- Модели (`ImageTask` уже содержит `is_hidden`, `status`, `operation`, таймштампы).
- Pydantic schemas (`ImageTaskListItem` уже отдаёт нужные поля).
- Миграции Alembic — не требуются.

## Тестирование

### Backend pytest

- **`backend/tests/test_image_permanent_delete.py`** (новый):
  - Happy path: delete → 200, запись удалена из БД, `uploads/{task_id}/` отсутствует.
  - 404 для чужого `user_id`.
  - 404 для несуществующего `task_id`.
  - Audit log создан.

- **Существующие тесты image-модуля** (`test_image_inpaint.py`, `test_image_preview_lookup.py`, `test_image_schema.py`) — не должны сломаться. При запуске всей pytest-сьюты из `backend/tests/` они должны оставаться зелёными.

### Frontend unit (Vitest — добавляется в рамках этого изменения)

Проект использует Vite, поэтому Vitest — естественный выбор (без отдельной сборки тестов, общий конфиг).

**Новые файлы/записи:**

- `frontend/package.json` — devDependencies: `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, `jsdom`. Скрипты: `"test": "vitest"`, `"test:run": "vitest run"`.
- `frontend/vite.config.ts` — расширяем `test` блоком (`environment: 'jsdom'`, `setupFiles: ['./src/test/setup.ts']`, `globals: true`).
- `frontend/src/test/setup.ts` — импортирует `@testing-library/jest-dom`; стабит глобальный `IntersectionObserver` (jsdom его не даёт).
- Обновить `frontend/tsconfig.json` (`types: ["vitest/globals", "@testing-library/jest-dom"]`).

**Тесты:**

- `ImageProgress.test.tsx`: рендерится корректно для каждой комбинации `(status, isHistory)` — набор кнопок, прогресс-бар, thumbnail/fallback; обработчики `onDismiss`, `onRestore`, `onDelete`, `onDownload` вызываются с `task_id`.
- `Thumbnail.test.tsx`: освобождает blob URL при unmount (spyOn `URL.revokeObjectURL`); fallback на иконку при 404; AbortController отменяет in-flight запрос при unmount.

### Ручная верификация

### Ручная верификация

- Загрузить изображение → удалить фон → после `ready` карточка в «Активных» → «Скрыть» → карточка в «Истории» → «Восстановить» → снова в «Активных».
- Permanent delete из истории: карточка исчезает, reload страницы не воскрешает.
- «Скрыть завершённые»: две ready-задачи, один клик, обе уехали в историю.
- Resume-after-reload: запустить обработку, перезагрузить страницу — карточка в «Активных» со статусом `processing`, polling продолжается.
- Thumbnail lazy-load: открыть историю с >10 элементами, убедиться по DevTools → Network, что preview-запросы идут по мере скролла.

## Edge cases

| Сценарий | Поведение |
|---|---|
| Закрыл страницу во время `POST /upload` | Задача в БД не создалась, ничего не висит |
| Закрыл страницу во время `processing` | BackgroundTask продолжается, статус в БД обновится; при reload — карточка в `tasks[]`, polling возобновляется |
| Dismiss `processing`-задачи | Кнопка отсутствует при `processing` — dismiss невозможен |
| TTL истёк между загрузкой и скачиванием | 404 от backend, toast «Возможно, файл уже удалён» |
| Два таба браузера открыты | Оба пулят одни задачи; лишний трафик приемлем для 1-5 юзеров |
| Permanent delete без confirm | Юзер может удалить случайно — accept-риск (решение C из Q6) |
| Switch между вкладками с current-task | При возврате вкладка читает `tasks[]` и видит актуальный статус |

## Явно вне scope

- Batch upload (несколько файлов за раз) — в Image Processor пока один файл на задачу, не меняем.
- Undo-toast для permanent-delete — опциональный stretch-goal.
- ZIP download для истории — не имеет смысла для image (файлы небольшие, разные операции).
- Изменение UX для `watermark` (mask-editing) — остаётся как сейчас.
- Миграция старых задач — не применимо, `ImageTask` схема уже совместима.

## Файлы к изменению / созданию — сводка

**Backend:**
- `backend/app/routers/image.py` — новый эндпоинт `DELETE /task/{id}/permanent`.
- `backend/app/services/image_service.py` — новая функция `delete_task_permanent`; при необходимости расширить фильтр в `get_user_tasks`.
- `backend/tests/test_image_permanent_delete.py` — новый.

**Frontend:**
- `frontend/src/pages/ImageProcessor/ImageProcessorPage.tsx` — полный рефактор.
- `frontend/src/pages/ImageProcessor/components/ImageProgress.tsx` — новый.
- `frontend/src/pages/ImageProcessor/components/ImageProgress.module.css` — новый.
- `frontend/src/pages/ImageProcessor/components/Thumbnail.tsx` — новый.
- `frontend/src/pages/ImageProcessor/components/BackgroundRemoval.tsx` — рефактор (убрать локальный polling, принять `currentTask` через props).
- `frontend/src/pages/ImageProcessor/components/WatermarkRemoval.tsx` — аналогично.
- `frontend/src/pages/ImageProcessor/imageApi.ts` — добавить `deleteTaskPermanent`.
- `frontend/src/pages/ImageProcessor/components/TaskHistory.tsx` — удалить.
- `frontend/src/pages/ImageProcessor/components/TaskHistory.module.css` — удалить.

**Frontend test infrastructure (Vitest):**
- `frontend/package.json` — добавить devDependencies и скрипты.
- `frontend/vite.config.ts` — добавить `test` блок.
- `frontend/tsconfig.json` — добавить `types` для Vitest / Testing Library.
- `frontend/src/test/setup.ts` — новый файл.
- `frontend/src/pages/ImageProcessor/components/ImageProgress.test.tsx` — новый.
- `frontend/src/pages/ImageProcessor/components/Thumbnail.test.tsx` — новый.
