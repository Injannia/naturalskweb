# Cosmic Redesign — Indigo Nebula

**Дата:** 2026-05-08
**Статус:** Дизайн согласован, ожидает финального ревью перед написанием плана реализации
**Скоуп:** Полная переработка визуального языка фронтенда NaturalskWeb с сохранением функционального поведения и API

## 1. Концепция

**Indigo Nebula** — тёмный космический визуальный язык, построенный на трёх осях:

1. **Глубокая тёмная база** (`#0B0B14`) с медленно дышащим mesh-градиентом в спектре индиго → виолет → магента.
2. **Стеклянные поверхности** (frosted glass с backdrop-blur 16–24px) для всех панелей и карточек, создающие ощущение многослойности.
3. **Aurora-акценты** — gradient `linear-gradient(135deg, #6366F1, #A855F7, #EC4899)` на CTA, focus-state, активных элементах и важных hero-надписях через `background-clip: text`.

Существующее звёздное поле сохраняется и эволюционирует: трёхслойная плотность, мерцание самых ярких звёзд, поверх — медленно двигающиеся aurora-blob'ы.

**Что меняется:** все CSS-токены, layout-каркас, все страницы, добавляется bottom-nav для мобильных.
**Что не меняется:** backend API, контракты эндпоинтов, логика модулей, auth-инвариант, polling, AvatarImage-поведение.

**Light mode не разрабатывается** — приложение dark-only.

## 2. Архитектура layout

### Desktop (≥768px)

- Sidebar 240px слева — стеклянный фон, blur 24px, тонкая aurora-граница справа.
- Topbar 56px сверху — стеклянный, blur 20px, тонкая aurora-граница снизу (1px gradient через `border-image`). При скролле фон уплотняется до `rgba(11,11,20,0.85)`.
- Активный пункт sidebar — стеклянный pill с мягким индиго-glow и индиго-точкой слева (вместо текущей рамки).

### Mobile (<768px)

- Sidebar полностью убирается с экрана (никаких drawer/hamburger).
- Topbar остаётся, но компактнее: только заголовок страницы + аватар.
- **Floating bottom-nav-pill** — стеклянная скруглённая полоса с отступом 12px от низа и боков, парящая над контентом. 4–5 иконок (Home, YouTube, Converter, Image, More). Активная иконка с aurora-glow и анимированной точкой-индикатором. Лейблы видны только у активного пункта.
- Пункты bottom-nav фильтруются по permissions (как текущий sidebar).
- `padding-bottom: env(safe-area-inset-bottom)` для iOS-устройств с home-индикатором.

## 3. Дизайн-токены

### Цвета

```css
/* Backgrounds */
--bg-base:       #0B0B14;
--bg-surface:    rgba(20, 20, 35, 0.6);    /* стеклянная карточка */
--bg-elevated:   rgba(28, 28, 50, 0.75);   /* модалки, поповеры */
--bg-input:      rgba(13, 13, 24, 0.6);
--bg-hover:      rgba(99, 102, 241, 0.08);

/* Borders */
--border:        rgba(255, 255, 255, 0.08);
--border-strong: rgba(255, 255, 255, 0.14);
--border-glow:   rgba(168, 85, 247, 0.45);

/* Text */
--text-primary:   #F8F8FC;
--text-secondary: #A4A4B8;
--text-muted:     #6B6B82;
--text-inverse:   #0B0B14;

/* Accents */
--accent-1: #6366F1;  /* индиго (primary CTA) */
--accent-2: #A855F7;  /* виолет (hover, secondary) */
--accent-3: #EC4899;  /* магента (highlights) */
--accent-gradient: linear-gradient(135deg, #6366F1 0%, #A855F7 50%, #EC4899 100%);

/* Glow tokens */
--glow-sm: 0 0 12px rgba(99, 102, 241, 0.35);
--glow-md: 0 0 24px rgba(168, 85, 247, 0.40);
--glow-lg: 0 0 48px rgba(168, 85, 247, 0.30), 0 0 96px rgba(236, 72, 153, 0.18);

/* Semantic (приглушены чтобы не конфликтовать с aurora) */
--success: #34D399;
--warning: #FBBF24;
--danger:  #F87171;

/* Shadows */
--shadow-sm:     0 2px 8px rgba(0, 0, 0, 0.4);
--shadow-md:     0 8px 32px rgba(11, 11, 20, 0.5);
--shadow-lg:     0 16px 48px rgba(11, 11, 20, 0.6);
--shadow-aurora: 0 12px 48px rgba(99, 102, 241, 0.18);

/* Radii */
--radius-sm:   6px;
--radius-md:   12px;
--radius-lg:   20px;
--radius-pill: 9999px;
```

### Типографика

- `--font-display`: `'Space Grotesk', system-ui` — логотип, h1/h2, hero-текст
- `--font-ui`: `'Inter', system-ui` — body, h3-h6, всё интерфейсное
- `--font-mono`: `'JetBrains Mono', monospace` — размеры файлов, длительности, ID, роли

**Шкала:** 12 / 14 / 16 / 20 / 24 / 32 / **40 (3xl)** / **56 (4xl)**.
**Заголовки** — weight 600, tracking `-0.02em`.
**Body** — weight 400, line-height 1.5.

Подключение: variable-fonts через Google Fonts с `font-display: swap`. Preload — Space Grotesk 600 + Inter 400.

### Spacing

4pt rhythm как сейчас (`--space-1` 0.25rem … `--space-12` 3rem) + `--space-16` (4rem) и `--space-20` (5rem) для hero-областей.

## 4. Компоненты-ядро

### Cards

`background: var(--bg-surface)`, `backdrop-filter: blur(20px)`, `border: 1px solid var(--border)`, `border-radius: var(--radius-lg)`.
**Hover:** `border-color: var(--border-glow)`, `--glow-sm`, `transform: translateY(-2px)`, переход 200ms ease-out. На карточках главных модулей при hover — едва видимый `--accent-gradient` как 1px-светящийся outline.

### Buttons

- **Primary CTA** — `background: var(--accent-gradient)`, белый текст, `--radius-md`, padding 10/16. Hover: насыщение +5%, `--glow-md`. Active: `transform: scale(0.98)`. Disabled: opacity 0.4.
- **Secondary** — стеклянный фон, `border: 1px solid var(--border-strong)`, текст primary. Hover: `border-color: var(--accent-1)`, `--glow-sm`.
- **Ghost** — без фона/рамки, текст secondary → primary на hover.
- **Danger** — `--danger` фон, белый текст; для второстепенных деструктивных — outlined в `--danger`.

Touch-target ≥ 44×44 везде.

### Inputs

`background: var(--bg-input)`, `border: 1px solid var(--border)`, `border-radius: var(--radius-md)`. Focus: `border-color: var(--accent-1)` + `box-shadow: 0 0 0 3px rgba(99,102,241,0.18)`. Лейбл — над полем (16px secondary). Ошибки — inline под полем (иконка + текст в `--danger`). Helper-text — 13px muted.

### Sidebar (desktop)

Стеклянный фон blur 24px, gradient-text логотип. Активный пункт — стеклянный pill + `--glow-sm` + индиго-точка слева. Hover — `--bg-hover`. Coming-soon badge — стеклянный, muted.

### Topbar

Стеклянный, blur 20px, тонкая aurora-граница снизу. Аватар — круг с gradient-обводкой при наличии аватара, без неё — иконка с `--accent-gradient` фоном. При скролле фон уплотняется.

### BottomNav (mobile, новый компонент)

Floating: 12px от боков и низа. `border-radius: --radius-pill` (по факту 28px), `background: rgba(20,20,35,0.7)`, `backdrop-filter: blur(28px)`, `border: 1px solid var(--border-strong)`, `--shadow-aurora`. Высота 56px, иконки 24px. Активная иконка — `--accent-gradient` через `mask-image`, под ней — мерцающая точка-индикатор. Лейбл активного пункта анимированно появляется.

### Modals

`--bg-elevated` фон, `--radius-lg`, `--shadow-aurora`. Backdrop — `rgba(11,11,20,0.6)` + 12px blur. Анимация: fade + scale 0.96→1 за 200ms ease-out, выход 150ms ease-in.

### Toasts (react-toastify overrides)

Стеклянные, `--bg-surface` + blur, `--radius-lg`, прогресс-бар `--accent-gradient`. Тип success/error/warning — иконка цветная.

### StarryBackground (эволюция существующего)

- Звёзд ×0.6 от текущего количества.
- Три слоя яркости: opacity 0.3 / 0.6 / 0.9.
- Самые яркие звёзды пульсируют 4-сек циклом (`opacity` 0.7→1.0).
- Без parallax.
- Поверх — отдельный слой с двумя aurora-blob'ами (~600px радиальные градиенты), медленно двигающимися по большим эллипсам через `transform: translate3d(...)` с 24-сек циклом.
- Mesh-градиент фона — отдельный слой с 18-сек циклом смены `background-position`, GPU-композитный (`transform: translateZ(0)`, `will-change: background-position`).

## 5. Страничные адаптации

### Home `/`

- **Hero-блок** по центру вверху (top-padding ~10vh desktop / 6vh mobile). Логотип «Naturalsk» (Space Grotesk 56–64px desktop / 36–40px mobile, weight 600), залитый `--accent-gradient` через `background-clip: text`. Под ним — приветствие `Привет, {username}` (Inter 18px secondary). Под приветствием — статус доступа (мелкий muted: «Все модули доступны» / «3 из 5 модулей»).
- **Грид модулей:** `grid-template-columns: repeat(auto-fit, minmax(260px, 1fr))`, gap 20px, max-width 1100px. Каждая плитка — стеклянная карточка с большой иконкой 44×44 (gradient-mask), заголовком (Space Grotesk 20px), описанием (Inter 14px secondary).
- **Mobile (<768px):** 1 колонка, плитки горизонтальной компоновки (иконка слева, текст справа).
- **Hover:** lift, рамка-glow, иконка saturate +20%, brightness +10%.
- ЛК и Admin Panel — отдельным рядом ниже основной сетки.

### Login `/login` и `/change-password`

- Центрированная стеклянная карточка (max-width 420px).
- Aurora-фон + звёзды видны полноэкранно (особенно на mobile).
- Сверху карточки — логотип Naturalsk с gradient-fill (меньше Hero-варианта).
- Поля и кнопка — компонентная база. Ошибки — inline под полем + общая полоса под формой при неверных кредах.
- Mobile: карточка занимает почти всю ширину (отступ 16px от краёв).

### Profile `/me`

- **Desktop (≥1024px):** двухколоночный layout. Слева — большая карточка аватара с gradient-обводкой и кнопками upload/crop/delete. Справа — стеклянные секции:
  - **Профиль** — username с inline-edit.
  - **Использование** — usage bars с aurora-gradient заполнением; при >80% — gradient становится оранжево-красным + glow.
  - **Активные сессии** — стеклянный список карточек сессий + кнопка «Завершить».
  - **Безопасность** — смена пароля.
- **Mobile:** одна колонка, секции стекаются вертикально.

### Модули — общая каркасная страница (YouTube, Converter, Image)

- Заголовок секции (Space Grotesk 24px) + опциональный subtitle.
- Основной рабочий блок в стеклянной карточке.
- **Drop-zones (Converter, Image):** пунктирная aurora-рамка (animated dash); на drag-over — рамка усиливается, фон карточки получает `--accent-glow` пульс.
- **Список загружаемых файлов:** стеклянные строки с прогрессбарами `--accent-gradient`.
- **YouTube:** input URL (с paste-кнопкой) + карточка превью видео + download-options как pill-кнопки.
- **Image processor:** before/after split-view со стеклянным разделителем (gradient-ручка).

### Admin `/admin`

- **Табы → segmented switcher:** стеклянная пилюля с 4 пунктами (users / audit / monitoring / profile), активный — `--accent-gradient` фон. Видимость пунктов фильтруется по роли: monitoring — только superadmin (как сейчас). На mobile (<640px) — горизонтальный скролл с snap-points.
- **Users:** data-grid в стеклянной карточке. Mobile: стек карточек (имя, роль, статус, действия). Действия per-row: edit, reset password, kill sessions, delete (модалки `EditUserModal`, `ResetPasswordModal`, `ConfirmDeleteModal` адаптируются под новый стиль модалок из Секции 4).
- **Audit:** список с virtual-scroll (если 1000+ записей), monospace timestamps, цветной chip типа действия.
- **Monitoring:** стат-карточки (CPU/RAM/Storage) с круговыми aurora-индикаторами; одна большая карточка «System»; sparkline графики с gradient-fill.
- **Profile (admin's own):** переиспользуем `ProfileTab` (тот же что в `/me`), уже импортируется `AdminPage.tsx` — без изменений в логике, только новый стиль через общие компоненты.

## 6. Анимации

### Длительности и easing

- Микро-интеракции: 150–200ms.
- Переходы карточек/модалок: 200–300ms.
- Mesh-фон: 18s loop.
- Aurora-blob'ы: 24s loop.
- Звёздное мерцание: 4s loop, рандомизированный delay.
- **Easing:** вход — `cubic-bezier(0.16, 1, 0.3, 1)`, выход — `cubic-bezier(0.4, 0, 1, 1)`. Никаких linear на UI-переходах. Выход на ~30% быстрее входа.

### Что анимируется

- Только `transform` и `opacity` (никогда `width/height/top/left`).
- Mesh-фон через `background-position` или CSS-переменные обновляемые `requestAnimationFrame`.

### Page transitions

Короткий fade + slide-up 4px, 180ms. Без сложных hero-transitions — внутренний инструмент, скорость важнее зрелищности.

### Reduced motion

При `prefers-reduced-motion: reduce` отключаем: mesh-движение фона, aurora-blob'ы, мерцание звёзд, hover-translate, page-transitions. Оставляем focus-ring transitions, hover-glow и instant state changes.

## 7. Доступность

- Все интерактивные элементы — focus-ring (2px solid `--accent-1` + 2px offset либо стеклянный glow-ring на тёмных поверхностях).
- Контрасты: primary text ≥7:1, secondary ≥4.5:1, UI-элементы ≥3:1. На стеклянных карточках — валидируем визуально (с blur-фоном за элементом).
- Каждой иконке — `aria-label` или sr-only текст.
- Активный пункт навигации — `aria-current="page"`.
- Цвет — никогда единственный носитель смысла: usage-bar > 80% получает иконку + красный; статус сессии — иконка + текст + цвет.
- Touch targets ≥ 44×44 везде; bottom-nav иконки — 56px hit-area.

## 8. Производительность

- `backdrop-filter: blur` ставим только на видимые/постоянные элементы (sidebar, topbar, bottom-nav, модалки, карточки на главной — в среднем 6–10 одновременно).
- На больших списках (audit log, sessions list) — обычный непрозрачный `--bg-surface`, без blur.
- Mesh-фон — один GPU-композитный слой (`transform: translateZ(0)`, `will-change: background-position`).
- Fallback на статический gradient (без анимации) для слабых устройств: детект через `navigator.deviceMemory < 2` или `connection.saveData`.
- Шрифты: variable-fonts, `font-display: swap`, preload только Space Grotesk 600 + Inter 400.
- **Без новых зависимостей:** не вводим framer-motion, GSAP, three.js. Всё на CSS + минимальном JS.

## 9. Скоуп изменений

### Что трогаем

1. **Глобальное:**
   - `frontend/src/styles/variables.css` — полная замена.
   - `frontend/src/styles/global.css` — новые шрифты, скроллбар, селекшен.
   - `frontend/src/index.css` — импорт шрифтов.
2. **Layout:** `MainLayout.tsx`, `Sidebar.tsx`, `Topbar.tsx`, `Layout.module.css`.
3. **Новый:** `BottomNav.tsx` + `BottomNav.module.css`. Рендерится из `MainLayout` параллельно с Sidebar.
4. **StarryBackground:** эволюция (aurora-blob слой, mesh-mask, ребаланс звёзд).
5. **Pages:**
   - **Home** — Hero + grid.
   - **Login / ChangePassword** — стеклянная карточка + полноэкранная aurora.
   - **Profile** — стеклянные секции, gradient-обводка аватара, aurora usage-bars.
   - **YouTube / Converter / Image** — общий каркас + drop-zones + кнопки/прогресс.
   - **Admin** — segmented switcher; users grid + cards на mobile; monitoring карточки с aurora-индикаторами.
6. **AvatarImage** — gradient-обводка опциональным prop'ом.
7. **Toastify overrides** — стеклянный стиль.

### Что НЕ трогаем

- Backend API, контракты эндпоинтов, миграции БД.
- Логика модулей (yt-dlp, ffmpeg, rembg, аутентификация, polling 15s, refresh-токен).
- Поведение AvatarImage (только визуал + новый prop).
- ProtectedRoute, useAuthProvider, api/client.
- Backend-тесты. Frontend-тесты могут потребовать обновления селекторов (CSS Modules переименования), но логика тестов не меняется.

## 10. Поэтапность реализации

В writing-plans разобьём на 4 фазы:

1. **Фаза 1 — фундамент:** токены + Layout (Sidebar / Topbar / новый BottomNav) + StarryBackground + Login/ChangePassword + Home.
2. **Фаза 2 — Profile + общие компоненты:** карточки, кнопки, поля, drop-zones (как переиспользуемые модули CSS).
3. **Фаза 3 — модули:** YouTube + Converter + Image.
4. **Фаза 4 — Admin:** все 4 таба + segmented switcher.

Каждая фаза валидируется через `bun run dev` + playwright-cli (skill) на ключевых сценариях; type-check через `bun run build`.

## 11. Anti-patterns (явно избегаем)

- Эмодзи как иконки (Lucide везде).
- Layout-сдвигающие hover-эффекты (только transform/opacity).
- Цвет как единственный носитель смысла.
- Хардкод hex в компонентах вместо токенов.
- Disabled animations при `prefers-reduced-motion: reduce` пропустить.
- `width/height/top/left` в анимациях.
- Введение новых JS-библиотек анимации (framer-motion и т.п.).
- Light mode прокидывать «на всякий случай» (приложение dark-only).
- Полупрозрачные карточки на больших списках без blur (получим грязь под текстом).
