# Image Processor — качество обработки и UX сравнения

**Дата:** 2026-04-19
**Статус:** утверждено для реализации
**Контекст:** пользовательский отчёт о плохой работе удаления фона и водяных знаков, неработающем методе Navier-Stokes и неудобном интерфейсе сравнения «До/После».

---

## Цель

Существенно повысить качество двух операций модуля Image Processor и переработать UI сравнения результата — всё под ограничения текущего железа (Intel Core i3-1005G1, 4 потока, 3.6 ГБ RAM, без NVIDIA GPU).

Пользователь явно указал приоритет качества над скоростью: латентность не критична, памяти — сколько поместится.

---

## Диагноз текущих проблем

1. **Удаление фона работает плохо.** Используется rembg с моделью `u2netp` — самая лёгкая модель семейства U²-Net (~4 МБ). Её точность существенно ниже современных альтернатив на универсальных сценариях (люди + товары + произвольные объекты).

2. **Удаление водяных знаков работает плохо.** Используется `cv2.inpaint` — классический алгоритм 2000-х, не обученный на реальных фото. На крупных знаках (диагональный текст, стикеры) даёт заметные артефакты независимо от флага.

3. **Метод Navier-Stokes «не работает».** TELEA и NS — оба классические алгоритмы, визуально дают почти идентичный результат на реальных фото. Создаётся впечатление, что NS не работает — на самом деле работают оба, просто одинаково посредственно. Вдобавок `inpaintRadius=3` жёстко зашит в коде — для крупных знаков этого мало.

4. **UI сравнения «До/После» неудобен.** Текущий `ImageCompare` использует слайдер-шторку, но с неочевидной семантикой: «До» расположено в правом нижнем углу, «После» — в левом нижнем. Плюс отсутствуют режимы «только До» / «только После», клавиатурная доступность и шахматка для прозрачного фона.

---

## Решение — высокий уровень

- **Удаление фона:** заменить `u2netp` на `birefnet-general-lite`, включить alpha matting и post-process mask.
- **Удаление водяных знаков:** добавить LaMa (через `simple-lama-inpainting`) как основной метод по умолчанию; TELEA и NS оставить как опции для мелких дефектов; добавить автоматическую дилатацию маски; увеличить `inpaintRadius` классических методов с 3 до 10.
- **UI сравнения:** переработать `ImageCompare` — добавить три режима (До / Сравнить / После), исправить семантику лейблов, добавить клавиатуру, добавить шахматку прозрачности для результатов с альфа-каналом.

---

## Backend

### Зависимости

Добавляется в `backend/requirements.txt`:

```
simple-lama-inpainting>=0.1.2
```

`rembg` уже присутствует — проверить, что версия ≥ 2.0.56 (поддержка `birefnet-general-lite`). При необходимости поднять.

`onnxruntime` подтягивается транзитивно обеими библиотеками.

### Модель rembg

В `app/services/image_service.py`:

```python
_REMBG_MODEL_NAME = "birefnet-general-lite"

def _get_rembg_session():
    global _rembg_session
    with _rembg_lock:
        if _rembg_session is None:
            from rembg import new_session
            _rembg_session = new_session(_REMBG_MODEL_NAME)
            logger.info("rembg %s session initialised", _REMBG_MODEL_NAME)
        return _rembg_session
```

### Функция `_remove_bg_sync`

Вызов `remove()` получает дополнительные параметры:

```python
output_bytes = remove(
    input_bytes,
    session=session,
    alpha_matting=True,
    alpha_matting_foreground_threshold=240,
    alpha_matting_background_threshold=10,
    alpha_matting_erode_size=10,
    post_process_mask=True,
)
```

Параметры alpha matting улучшают края волос/меха/полупрозрачных областей за счёт дополнительного прохода (тримап-декомпозиция). На CPU это ~2–3× медленнее — допустимо.

### LaMa: ленивая инициализация

В `image_service.py` появляется отдельная глобальная ссылка и lock:

```python
_lama_model = None
_lama_lock = threading.Lock()

def _get_lama_model():
    global _lama_model
    with _lama_lock:
        if _lama_model is None:
            from simple_lama_inpainting import SimpleLama
            _lama_model = SimpleLama()
            logger.info("LaMa model initialised")
        return _lama_model
```

### Схема `InpaintMethod`

В `app/schemas/image.py` тип расширяется:

```python
InpaintMethod = Literal["lama", "telea", "ns"]
```

Миграция БД не нужна: `inpaint_method` хранится как `String`.

### Функция `_remove_watermark_sync`

Логика сбора маски из `shapes` сохраняется. После построения маски добавляется два шага:

1. **Дилатация** — чтобы пользователю не требовалось рисовать строго по контуру:

```python
kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
mask = cv2.dilate(mask, kernel, iterations=1)
```

2. **Выбор пути обработки по методу:**

```python
if inpaint_method == "lama":
    from PIL import Image
    h, w = img.shape[:2]
    # Даунсемплинг для LaMa при больших размерах
    MAX_LAMA_SIDE = 1536
    scale = min(MAX_LAMA_SIDE / max(h, w), 1.0)
    if scale < 1.0:
        new_w, new_h = int(w * scale), int(h * scale)
        img_for_lama = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        mask_for_lama = cv2.resize(mask, (new_w, new_h), interpolation=cv2.INTER_NEAREST)
    else:
        img_for_lama = img
        mask_for_lama = mask

    pil_img = Image.fromarray(cv2.cvtColor(img_for_lama, cv2.COLOR_BGR2RGB))
    pil_mask = Image.fromarray(mask_for_lama)
    lama = _get_lama_model()
    result_pil = lama(pil_img, pil_mask)

    if scale < 1.0:
        result_pil = result_pil.resize((w, h), Image.LANCZOS)

    result = cv2.cvtColor(np.array(result_pil), cv2.COLOR_RGB2BGR)
else:
    flags = cv2.INPAINT_TELEA if inpaint_method == "telea" else cv2.INPAINT_NS
    result = cv2.inpaint(img, mask, 10, flags)  # было 3
```

### Прогрев моделей при старте

В `app/main.py`, в `lifespan`, запускается фоновый прогрев:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    async def _warmup():
        from app.services import image_service
        try:
            await asyncio.to_thread(image_service._get_rembg_session)
            await asyncio.to_thread(image_service._get_lama_model)
        except Exception:
            logger.exception("Model warmup failed")
    asyncio.create_task(_warmup())
    yield
```

Прогрев не блокирует старт приложения. Ошибка прогрева логируется, но не останавливает сервер — модели всё равно инициализируются лениво при первом запросе.

### Управление памятью — план отката

BiRefNet-lite + alpha matting может потребовать ~1.5–2 ГБ пиково. При тестировании на реальном железе (2.4 ГБ RAM свободно) возможен OOM. Путь отката — без изменения логики:

- Если BiRefNet-lite не помещается → константу `_REMBG_MODEL_NAME = "isnet-general-use"` (~170 МБ, ниже качество, но заметно легче по памяти).
- Если alpha matting вызывает OOM → отключить флаг `alpha_matting`.

Оба варианта — одностроковые правки, не требуют изменения API.

---

## Frontend

### Типы

В `frontend/src/pages/ImageProcessor/types.ts`:

```ts
export type InpaintMethod = 'lama' | 'telea' | 'ns'
```

### `WatermarkRemoval.tsx`

Дефолт метода меняется на `'lama'`:

```ts
const [inpaintMethod, setInpaintMethod] = useState<InpaintMethod>('lama')
```

`<select>` с подписями для понимания:

```tsx
<select
  className={styles.methodSelect}
  value={inpaintMethod}
  onChange={(e) => setInpaintMethod(e.target.value as InpaintMethod)}
  title="Метод инпейнтинга"
>
  <option value="lama">LaMa (нейросеть, рекомендуется)</option>
  <option value="telea">TELEA (быстрый классический)</option>
  <option value="ns">Navier-Stokes (классический)</option>
</select>
```

Под селектом — короткая памятка в `var(--text-secondary)`, `var(--fs-xs)`:

> LaMa даёт лучший результат для крупных и сложных знаков. Классические методы работают быстрее на мелких дефектах.

В фазе `processing` — если выбран `lama`, показывается подпись под прогрессбаром:

> LaMa работает локально на CPU и может занять до минуты.

### `ImageCompare.tsx` — переработка

**Новый интерфейс:**

```ts
interface ImageCompareProps {
  beforeSrc: string
  afterSrc: string
  beforeLabel?: string      // дефолт 'До'
  afterLabel?: string       // дефолт 'После'
  transparencyGrid?: boolean // дефолт false — шашечка для прозрачности
}
```

`BackgroundRemoval.tsx` передаёт `transparencyGrid={true}`.

**Три режима отображения:**

Сегментированный переключатель сверху компонента (React state `mode: 'before' | 'compare' | 'after'`, дефолт `'compare'`):

- `before` — только `beforeSrc` на всю область
- `compare` — слайдер-шторка (поведение по умолчанию)
- `after` — только `afterSrc` на всю область

Кнопки переключателя — иконки + подпись, в стиле существующих `toolBtn` из `WatermarkRemoval.module.css`.

**Исправление семантики лейблов в режиме `compare`:**

Сейчас `afterWrapper` с `left: 0` шторится слева направо, но «После» стоит в левом нижнем углу, а «До» — в правом нижнем. Пользователь ожидает обратного (слева = «До», справа = «После»), как в большинстве референсов.

Решение — инвертировать, какая картинка кладётся сверху: **`beforeWrapper` сверху, шторится справа налево**. Тогда при `position: 50%` левая половина показывает `beforeSrc` (под шторкой), правая — `afterSrc` (свободная). Лейблы: «До» в левом верхнем углу, «После» в правом верхнем.

Альтернатива — оставить `afterWrapper` сверху, но поменять лейблы местами. Выбран первый вариант, потому что он семантически корректен: шторка «открывает После, пока не сдвинули влево» — это привычно.

Точная реализация (псевдокод):

```tsx
// after — фоновый слой на всю область
<img src={afterSrc} className={styles.image} />

// before — клипается по ширине от левого края
<div
  className={styles.beforeWrapper}
  style={{ width: `${position}%` }}
>
  <img src={beforeSrc} className={styles.image} />
</div>
```

CSS для `beforeWrapper` аналогичен текущему `afterWrapper`, включая `100cqw` для предотвращения сжатия картинки.

**Клавиатура и ARIA:**

Ручка слайдера получает:

```tsx
<div
  role="slider"
  tabIndex={0}
  aria-label="Позиция сравнения"
  aria-valuenow={Math.round(position)}
  aria-valuemin={0}
  aria-valuemax={100}
  onKeyDown={handleKeyDown}
>
```

Обработчик клавиатуры:

- `←` / `→` — ±2 %
- `Shift+←` / `Shift+→` — ±10 %
- `Home` — 0 %
- `End` — 100 %

**Шашечка прозрачности:**

При `transparencyGrid={true}` контейнер получает CSS background с 16×16 px шашечкой (два оттенка серого). Используется для корректного отображения PNG с альфа-каналом из удаления фона.

**Визуальные полировки:**

- Ручка слайдера 40 px (было 32), более заметная тень
- Лейблы перемещены в верхние углы в режиме `compare`
- В режимах `before` / `after` — один крупный лейбл в левом верхнем углу с названием текущего режима

### `TaskHistory.tsx`

Если в компоненте есть маппинг названий методов в человекочитаемые строки — добавить `'lama' → 'LaMa'`. Проверить при реализации; возможно, таблица-маппинг уже универсальна и просто показывает строку метода.

---

## Тестирование

### Backend-тесты (pytest)

Новый файл `backend/tests/test_image_service_inpaint.py` или расширение существующего (если есть):

1. **`_remove_watermark_sync` с `lama`** — мок `_get_lama_model` возвращает объект с `__call__`, возвращающим фиктивный `PIL.Image`. Проверяем:
   - `cv2.dilate` вызван с корректным kernel
   - При входе > 1536 px по большей стороне применён даунсемплинг (через spy на `cv2.resize`)
   - Результат сохранён в `{uuid}.png`

2. **`_remove_watermark_sync` с `telea`** — проверка, что `cv2.inpaint` вызван с `inpaintRadius=10` (не 3).

3. **`_remove_watermark_sync` с `ns`** — то же для `cv2.INPAINT_NS`.

4. **Schema validation** — pydantic-тест: `{"inpaint_method": "lama"}` валиден, `{"inpaint_method": "unknown"}` → 422.

5. **Smoke-тест `@pytest.mark.slow`** (опционально, не в CI по умолчанию): реальный прогон LaMa на 64×64 картинке, проверка, что result.size == input.size и что в маскированной области пиксели изменились.

Реальные прогоны rembg и LaMa в обычных unit-тестах **не делаются** — требуют скачивания весов, медленно для CI. Только моки.

### Frontend

Если в `frontend/tests/` (Playwright) есть e2e для Image Processor — проверить и при необходимости обновить ожидания. Новые e2e-сценарии не добавляем сверх необходимого для покрытия изменений (переключатель режимов, выбор LaMa).

---

## Критерии приёмки

- [ ] Удаление фона заметно лучше на портретах и универсальных фото — края волос и объектов чётче
- [ ] Удаление водяных знаков с методом LaMa убирает крупные знаки без видимых артефактов
- [ ] TELEA и NS остаются доступными как опции с `inpaintRadius=10`
- [ ] Маска автоматически дилатируется на ~5 px
- [ ] В UI сравнения слева показан оригинал, справа — результат (ожидаемая семантика)
- [ ] Три режима переключения: «До», «Сравнить», «После»
- [ ] Клавиатурная навигация работает: `←/→`, `Shift+←/→`, `Home`, `End`
- [ ] Результат с прозрачным фоном показывается на шашечке
- [ ] Прогрев моделей при старте приложения не блокирует запуск
- [ ] Все существующие тесты проходят; добавлены новые unit-тесты на ветви LaMa/TELEA/NS

## Риски и их смягчение

| Риск | Вероятность | Смягчение |
|------|-------------|-----------|
| BiRefNet-lite + alpha matting не помещается в 2.4 ГБ RAM | Средняя | Откат на `isnet-general-use` или отключение `alpha_matting` |
| LaMa на CPU слишком медленная (> 60 сек) | Низкая | Даунсемплинг до 1536 px уже в плане |
| `simple-lama-inpainting` тянет тяжёлые транзитивные зависимости (torch) | Средняя | Проверить размер установки; при необходимости — прямой ONNX-вызов через onnxruntime |
| Первая загрузка моделей (~290 МБ) в проде без доступа в интернет | Низкая | Предзагрузить модели при сборке образа / пропустить через прокси |

---

## Вне области изменений

- Модель задач, БД, Alembic-миграции
- Аутентификация, квоты, история задач
- `MaskCanvas` (логика рисования маски) — не трогаем
- API-контракт эндпоинтов — меняется только enum допустимых значений `inpaint_method`
- Модуль Converter и YouTube — полностью не затрагиваются
