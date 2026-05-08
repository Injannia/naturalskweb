# Cosmic Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Полностью переработать визуальный язык фронтенда NaturalskWeb (Indigo Nebula — стеклянные поверхности, aurora mesh-фон, bottom-nav на мобильных) без изменений в backend, контрактах API и логике модулей.

**Architecture:** CSS-first подход через переработку токенов в `variables.css` + новый набор UI-компонентов в `frontend/src/components/ui/` (Button, Card, Input, DropZone), которые поэтапно подменяют inline-стили на страницах. Layout получает новый `BottomNav` для мобильных, sidebar/topbar — стеклянный стиль. Добавляется отдельный `AuroraBackground` поверх существующего `StarryBackground`. Реализация — 4 фазы по визуальной поверхности (фундамент → профиль/UI-kit → модули → админка), 15 задач, каждая коммитабельна и верифицируется через `bun run build` + playwright-cli skill.

**Tech Stack:** React 18 + TypeScript + Vite + CSS Modules + Lucide icons. Без новых JS-зависимостей. Шрифты — Google Fonts (Space Grotesk + Inter + JetBrains Mono variable).

**Спецификация:** [docs/superpowers/specs/2026-05-08-cosmic-redesign-design.md](../specs/2026-05-08-cosmic-redesign-design.md)

---

## Общие принципы выполнения

- **Один коммит на задачу.** Каждая задача завершается одним фокусированным коммитом с conventional-commit-сообщением.
- **Verify через build, а не через unit-тесты.** Это редизайн, логика не меняется. Type-check (`bun run build` или `npx tsc --noEmit`) — обязателен. Поведенческая проверка — через playwright-cli skill (snapshot ключевых страниц).
- **CSS Modules сохраняются.** Не вводим Tailwind/styled-components. Все стили — через `*.module.css`.
- **Новые шрифты подключаются один раз** в Задаче 1 и используются токенами `--font-display`, `--font-ui`, `--font-mono` во всех модулях.
- **UI-kit (Задача 7)** — точка ввода переиспользуемых компонентов. Все следующие задачи (8–15) импортируют из `frontend/src/components/ui/`.
- **Reduced-motion обязателен** в каждом блоке анимации: оборачиваем все `@keyframes` и `transform`/`background-position` транзишены в `@media (prefers-reduced-motion: no-preference)`.

---

## Файловая структура (что создаём, что меняем)

**Создаём:**
- `frontend/src/components/AuroraBackground/AuroraBackground.tsx` + `AuroraBackground.module.css` — отдельный слой mesh-градиента + aurora-blob'ов, рендерится поверх `StarryBackground`.
- `frontend/src/components/Layout/BottomNav.tsx` + добавление стилей в `Layout.module.css` — мобильная навигация-пилюля.
- `frontend/src/components/ui/Button.tsx` + `Button.module.css`
- `frontend/src/components/ui/Card.tsx` + `Card.module.css`
- `frontend/src/components/ui/Input.tsx` + `Input.module.css`
- `frontend/src/components/ui/DropZone.tsx` + `DropZone.module.css`
- `frontend/src/components/ui/index.ts` — barrel export.

**Полностью переписываем (CSS):**
- `frontend/src/styles/variables.css` — все токены.
- `frontend/src/styles/global.css` — фон body, скроллбар, селекшен, focus styles, шрифты, toastify overrides.
- `frontend/src/index.html` (`frontend/index.html`) — `<link>` preload шрифтов.

**Модифицируем (TSX + CSS):**
- `frontend/src/components/StarryBackground/StarryBackground.tsx` — снижение плотности, трёхслойность.
- `frontend/src/components/Layout/MainLayout.tsx` — рендер `AuroraBackground` + `BottomNav`.
- `frontend/src/components/Layout/Sidebar.tsx`, `Topbar.tsx`, `Layout.module.css` — стеклянный стиль, gradient-логотип.
- `frontend/src/components/AvatarImage.tsx` + `.module.css` — опциональный prop `accentBorder` для gradient-обводки.
- `frontend/src/pages/Home/HomePage.tsx` + `Home.module.css` — Hero + стеклянные плитки.
- `frontend/src/pages/Login/LoginPage.tsx` + `LoginPage.module.css` — стеклянная карточка.
- `frontend/src/pages/ChangePassword/ChangePasswordPage.tsx` + `.module.css` — то же.
- `frontend/src/pages/Profile/*` — все 7 файлов профиля.
- `frontend/src/pages/YouTube/*` — 6 модулей.
- `frontend/src/pages/Converter/*` — 5 модулей.
- `frontend/src/pages/ImageProcessor/*` — 8 модулей (включая `components/`).
- `frontend/src/pages/Admin/*` — 8 файлов.

**Не трогаем:**
- `frontend/src/api/*`, `frontend/src/hooks/*`, `frontend/src/stores/*`, `frontend/src/types/*`.
- `frontend/src/components/ProtectedRoute.tsx`, `PlaceholderPage.tsx`.
- Backend целиком (`backend/`).
- `frontend/src/test/*` (структура), но `.test.tsx` могут потребовать обновлений селекторов — это локально внутри задач 11.

---

## Phase 1 — Фундамент

### Task 1: Дизайн-токены и шрифты

**Goal:** Заменить `variables.css` на палитру Indigo Nebula, подключить Space Grotesk + Inter + JetBrains Mono через Google Fonts, обновить базовый `global.css` под новые токены.

**Files:**
- Modify: `frontend/src/styles/variables.css` (полная замена)
- Modify: `frontend/src/styles/global.css` (фон, шрифт, скроллбар, селекшен, focus, toastify)
- Modify: `frontend/index.html` (preload + link на Google Fonts)

**Acceptance Criteria:**
- [ ] `variables.css` содержит все токены палитры из спека (раздел «Цвета» Секции 3 спека).
- [ ] `--font-display`, `--font-ui`, `--font-mono` определены и Space Grotesk/Inter/JetBrains Mono загружаются.
- [ ] `body` использует `--bg-base` и `--font-ui`.
- [ ] Скроллбар стеклянный (`--border-strong` thumb), селекшен использует `--accent-2`.
- [ ] Focus-ring глобально — `2px solid var(--accent-1)` + `outline-offset: 2px`.
- [ ] `bun run build` проходит без ошибок.

**Verify:**
```
cd frontend && bun run build
```
Ожидание: `tsc && vite build` завершается без ошибок, в `dist/` появляется новый билд.

**Steps:**

- [ ] **Step 1: Подключить шрифты в `frontend/index.html`.**

В `<head>` (после viewport-meta) добавить:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preload" as="style" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&family=JetBrains+Mono:wght@400;500&display=swap">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&family=JetBrains+Mono:wght@400;500&display=swap">
```

- [ ] **Step 2: Полная замена `frontend/src/styles/variables.css`.**

```css
:root {
  /* ── Backgrounds ── */
  --bg-base: #0B0B14;
  --bg-surface: rgba(20, 20, 35, 0.6);
  --bg-elevated: rgba(28, 28, 50, 0.75);
  --bg-input: rgba(13, 13, 24, 0.6);
  --bg-hover: rgba(99, 102, 241, 0.08);

  /* ── Borders ── */
  --border: rgba(255, 255, 255, 0.08);
  --border-strong: rgba(255, 255, 255, 0.14);
  --border-glow: rgba(168, 85, 247, 0.45);

  /* ── Text ── */
  --text-primary: #F8F8FC;
  --text-secondary: #A4A4B8;
  --text-muted: #6B6B82;
  --text-inverse: #0B0B14;

  /* ── Accents (Aurora) ── */
  --accent-1: #6366F1;
  --accent-2: #A855F7;
  --accent-3: #EC4899;
  --accent-gradient: linear-gradient(135deg, #6366F1 0%, #A855F7 50%, #EC4899 100%);
  --accent-glow: rgba(99, 102, 241, 0.18);

  /* ── Glow ── */
  --glow-sm: 0 0 12px rgba(99, 102, 241, 0.35);
  --glow-md: 0 0 24px rgba(168, 85, 247, 0.40);
  --glow-lg: 0 0 48px rgba(168, 85, 247, 0.30), 0 0 96px rgba(236, 72, 153, 0.18);

  /* ── Semantic ── */
  --success: #34D399;
  --success-bg: rgba(52, 211, 153, 0.10);
  --warning: #FBBF24;
  --warning-bg: rgba(251, 191, 36, 0.10);
  --danger: #F87171;
  --danger-bg: rgba(248, 113, 113, 0.10);
  --danger-hover: #EF4444;

  /* ── Starfield (legacy) ── */
  --star: #ffffff;
  --star-glow: rgba(168, 85, 247, 0.20);

  /* ── Typography ── */
  --font-display: 'Space Grotesk', system-ui, -apple-system, sans-serif;
  --font-ui: 'Inter', system-ui, -apple-system, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
  --fs-xs: 0.75rem;
  --fs-sm: 0.875rem;
  --fs-base: 1rem;
  --fs-lg: 1.25rem;
  --fs-xl: 1.5rem;
  --fs-2xl: 2rem;
  --fs-3xl: 2.5rem;
  --fs-4xl: 3.5rem;

  /* ── Spacing (4pt rhythm) ── */
  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 0.75rem;
  --space-4: 1rem;
  --space-5: 1.25rem;
  --space-6: 1.5rem;
  --space-8: 2rem;
  --space-10: 2.5rem;
  --space-12: 3rem;
  --space-16: 4rem;
  --space-20: 5rem;

  /* ── Radii ── */
  --radius-sm: 6px;
  --radius-md: 12px;
  --radius-lg: 20px;
  --radius-pill: 9999px;

  /* ── Layout ── */
  --sidebar-width: 240px;
  --topbar-height: 56px;
  --bottomnav-height: 64px;

  /* ── Shadows ── */
  --shadow-sm: 0 2px 8px rgba(0, 0, 0, 0.4);
  --shadow-md: 0 8px 32px rgba(11, 11, 20, 0.5);
  --shadow-lg: 0 16px 48px rgba(11, 11, 20, 0.6);
  --shadow-aurora: 0 12px 48px rgba(99, 102, 241, 0.18);

  /* ── Transitions ── */
  --transition-fast: 150ms cubic-bezier(0.16, 1, 0.3, 1);
  --transition-base: 200ms cubic-bezier(0.16, 1, 0.3, 1);
  --transition-slow: 300ms cubic-bezier(0.16, 1, 0.3, 1);
  --transition-out: 150ms cubic-bezier(0.4, 0, 1, 1);
}
```

- [ ] **Step 3: Переписать `frontend/src/styles/global.css`.**

```css
@import './variables.css';

*, *::before, *::after {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html {
  font-size: 16px;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
}

body {
  font-family: var(--font-ui);
  background: var(--bg-base);
  color: var(--text-primary);
  line-height: 1.5;
  min-height: 100vh;
  overflow-x: hidden;
}

#root {
  min-height: 100vh;
  position: relative;
  z-index: 1;
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
  background: var(--border-strong);
  border-radius: var(--radius-pill);
}
::-webkit-scrollbar-thumb:hover { background: var(--accent-1); }

/* ── Selection ── */
::selection {
  background: var(--accent-2);
  color: var(--text-primary);
}

/* ── Links ── */
a {
  color: var(--accent-1);
  text-decoration: none;
  transition: color var(--transition-fast);
}
a:hover { color: var(--accent-2); }

/* ── Focus ── */
:focus-visible {
  outline: 2px solid var(--accent-1);
  outline-offset: 2px;
  border-radius: var(--radius-sm);
}

img { max-width: 100%; display: block; }
code, pre, .mono { font-family: var(--font-mono); }

/* ── Animations ── */
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes slideUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
@keyframes pulseGlow {
  0%, 100% { box-shadow: var(--glow-sm); }
  50% { box-shadow: var(--glow-md); }
}
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

/* ── Toastify overrides (стеклянные тосты) ── */
.Toastify__toast-container { z-index: 100000; }
.Toastify__toast {
  background: var(--bg-elevated) !important;
  backdrop-filter: blur(20px) !important;
  -webkit-backdrop-filter: blur(20px) !important;
  color: var(--text-primary) !important;
  border: 1px solid var(--border-strong) !important;
  border-radius: var(--radius-lg) !important;
  font-family: var(--font-ui) !important;
  font-size: var(--fs-sm) !important;
  box-shadow: var(--shadow-aurora) !important;
}
.Toastify__close-button { color: var(--text-secondary) !important; }
.Toastify__progress-bar { background: var(--accent-gradient) !important; }
.Toastify__toast--success .Toastify__progress-bar { background: var(--success) !important; }
.Toastify__toast--error .Toastify__progress-bar { background: var(--danger) !important; }
.Toastify__toast--warning .Toastify__progress-bar { background: var(--warning) !important; }

/* ── Reduced motion ── */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

- [ ] **Step 4: Type-check.**

Run: `cd frontend && bun run build`
Expected: Без ошибок (предупреждение о CSS unused vars допустимо).

- [ ] **Step 5: Commit.**

```bash
git add frontend/index.html frontend/src/styles/variables.css frontend/src/styles/global.css
git commit -m "feat(ui): add Indigo Nebula tokens and Aurora typography"
```

---

### Task 2: AuroraBackground + StarryBackground v2

**Goal:** Создать новый компонент `AuroraBackground` (mesh-градиент + двух aurora-blob'ов) и снизить плотность звёзд в `StarryBackground` для трёхслойного эффекта. Оба компонента рендерятся параллельно в `MainLayout` и на `/login`/`/change-password`.

**Files:**
- Create: `frontend/src/components/AuroraBackground/AuroraBackground.tsx`
- Create: `frontend/src/components/AuroraBackground/AuroraBackground.module.css`
- Modify: `frontend/src/components/StarryBackground/StarryBackground.tsx` (плотность ×0.6, три слоя яркости)
- Modify: `frontend/src/components/Layout/MainLayout.tsx` (рендер `AuroraBackground` рядом со `StarryBackground`)
- Modify: `frontend/src/pages/Login/LoginPage.tsx` и `frontend/src/pages/ChangePassword/ChangePasswordPage.tsx` — если они рендерят свой `StarryBackground`, добавить и `AuroraBackground` (см. Step 4 — сначала проверить).

**Acceptance Criteria:**
- [ ] Компонент `AuroraBackground` рендерит два конкурирующих градиентных blob'а через `radial-gradient` + animated `transform: translate3d`.
- [ ] Mesh-фон body — через `linear-gradient` слой с `background-size: 200% 200%` и `animation: meshFlow 18s ease infinite`.
- [ ] `StarryBackground` плотность снижена до `Math.min(240, Math.max(120, area / 8000))`, звёзды разделены на три яркости.
- [ ] При `prefers-reduced-motion: reduce` все анимации фона отключаются.
- [ ] z-index: aurora `0`, stars `1`, content `>= 2`.
- [ ] `bun run build` проходит.

**Verify:**
```
cd frontend && bun run build
```

**Steps:**

- [ ] **Step 1: Создать `AuroraBackground.module.css`.**

```css
.layer {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
}

.mesh {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse 80% 60% at 20% 30%, rgba(99, 102, 241, 0.18), transparent 60%),
    radial-gradient(ellipse 70% 50% at 80% 70%, rgba(168, 85, 247, 0.14), transparent 60%),
    radial-gradient(ellipse 60% 40% at 50% 90%, rgba(236, 72, 153, 0.10), transparent 60%);
  background-size: 200% 200%;
  background-position: 0% 0%;
  animation: meshFlow 18s ease-in-out infinite;
  will-change: background-position;
}

.blob {
  position: absolute;
  width: 600px;
  height: 600px;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.55;
  will-change: transform;
}

.blob1 {
  background: radial-gradient(circle, rgba(99, 102, 241, 0.45), transparent 70%);
  top: -200px;
  left: -150px;
  animation: blobDrift1 24s ease-in-out infinite;
}

.blob2 {
  background: radial-gradient(circle, rgba(236, 72, 153, 0.38), transparent 70%);
  bottom: -250px;
  right: -180px;
  animation: blobDrift2 28s ease-in-out infinite;
}

@keyframes meshFlow {
  0%, 100% { background-position: 0% 0%; }
  50% { background-position: 100% 100%; }
}

@keyframes blobDrift1 {
  0%, 100% { transform: translate3d(0, 0, 0) scale(1); }
  33% { transform: translate3d(120px, 80px, 0) scale(1.08); }
  66% { transform: translate3d(60px, 160px, 0) scale(0.96); }
}

@keyframes blobDrift2 {
  0%, 100% { transform: translate3d(0, 0, 0) scale(1); }
  33% { transform: translate3d(-100px, -60px, 0) scale(1.05); }
  66% { transform: translate3d(-160px, 40px, 0) scale(0.92); }
}

@media (prefers-reduced-motion: reduce) {
  .mesh, .blob1, .blob2 { animation: none; }
}
```

- [ ] **Step 2: Создать `AuroraBackground.tsx`.**

```tsx
import styles from './AuroraBackground.module.css'

export default function AuroraBackground() {
  return (
    <div className={styles.layer} aria-hidden="true">
      <div className={styles.mesh} />
      <div className={`${styles.blob} ${styles.blob1}`} />
      <div className={`${styles.blob} ${styles.blob2}`} />
    </div>
  )
}
```

- [ ] **Step 3: Обновить `StarryBackground.tsx`.**

В функции `initStars` заменить плотность:

```tsx
const count = Math.min(
  240,
  Math.max(120, Math.floor((canvas!.width * canvas!.height) / 8000)),
)
```

В цикле создания звёзд распределить три уровня яркости:

```tsx
stars = Array.from({ length: count }, () => {
  const tier = Math.random()
  const opacity = tier < 0.5 ? Math.random() * 0.2 + 0.2  // dim 0.2-0.4
                : tier < 0.85 ? Math.random() * 0.2 + 0.5  // mid 0.5-0.7
                : Math.random() * 0.15 + 0.8              // bright 0.8-0.95
  return {
    x: Math.random() * canvas!.width,
    y: Math.random() * canvas!.height,
    size: Math.random() * 1.6 + 0.4,
    opacity,
    twinkleSpeed: Math.random() * 0.015 + 0.004,
    twinklePhase: Math.random() * Math.PI * 2,
  }
})
```

Также во вложенный обработчик: для самых ярких (`opacity > 0.75`) сохранить glow-halo (как сейчас, но с цветом `rgba(168, 85, 247, ...)` вместо текущего синего `(110, 123, 255, ...)`):

```tsx
if (star.opacity > 0.75) {
  ctx!.beginPath()
  ctx!.arc(star.x, star.y, star.size * 2.5, 0, Math.PI * 2)
  ctx!.fillStyle = `rgba(168, 85, 247, ${alpha * 0.10})`
  ctx!.fill()
}
```

В JSX-возврате обернуть `style.zIndex` в `1` вместо `0`:

```tsx
style={{
  position: 'fixed',
  top: 0,
  left: 0,
  width: '100%',
  height: '100%',
  zIndex: 1,
  pointerEvents: 'none',
  willChange: 'transform',
}}
```

- [ ] **Step 4: Обновить `MainLayout.tsx`.**

Импортировать `AuroraBackground` и рендерить его перед `StarryBackground`:

```tsx
import AuroraBackground from '../AuroraBackground/AuroraBackground'
// ...
return (
  <>
    <AuroraBackground />
    <StarryBackground />
    <div className={styles.layout}>
      {/* ... */}
    </div>
  </>
)
```

Если `LoginPage.tsx`/`ChangePasswordPage.tsx` рендерят свой `StarryBackground` — добавить туда же `AuroraBackground` перед ним. (Проверить: `rg "StarryBackground" frontend/src/pages/`.)

- [ ] **Step 5: Type-check + смотрим в браузере.**

Run: `cd frontend && bun run build` — без ошибок.

Run: `cd frontend && bun run dev` (фон) — открыть `http://localhost:5173/` (если залогинен) и убедиться визуально, что виден mesh-фон + звёзды + два медленно двигающихся blob'а. Можно через playwright-cli skill сделать snapshot.

- [ ] **Step 6: Commit.**

```bash
git add frontend/src/components/AuroraBackground frontend/src/components/StarryBackground frontend/src/components/Layout/MainLayout.tsx
# плюс LoginPage/ChangePasswordPage если меняли
git commit -m "feat(ui): add Aurora mesh background and rebalance starfield"
```

---

### Task 3: Sidebar + Topbar — стеклянный стиль

**Goal:** Переработать desktop-навигацию: стеклянные фоны с blur, gradient-логотип, активный пункт sidebar — стеклянный pill с glow и индиго-точкой слева, topbar — компактнее на mobile, тонкая aurora-граница снизу.

**Files:**
- Modify: `frontend/src/components/Layout/Layout.module.css` (полная переработка стилей sidebar/topbar)
- Modify: `frontend/src/components/Layout/Sidebar.tsx` (gradient на `Naturalsk`, добавить `aria-current` через `NavLink end` уже есть; добавить точку через CSS `:before` на `.navItemActive`)
- Modify: `frontend/src/components/Layout/Topbar.tsx` (опционально: scroll-detection через `useEffect` для `topbarScrolled` класса)

**Acceptance Criteria:**
- [ ] Sidebar: фон `var(--bg-surface)`, `backdrop-filter: blur(24px)`, тонкая `border-right` с `--border`.
- [ ] Логотип `Naturalsk*Web*` рендерится через `background: var(--accent-gradient); background-clip: text; color: transparent;`.
- [ ] Active nav-item: стеклянный pill (`background: var(--bg-hover)`, `border: 1px solid var(--border-glow)`), `box-shadow: var(--glow-sm)`, и `::before` псевдо-элемент — индиго-точка 4px слева.
- [ ] Topbar: фон `rgba(11, 11, 20, 0.5)` + `backdrop-filter: blur(20px)`, `border-bottom: 1px solid var(--border)`, аватар-обводка через `--accent-gradient` (используем `padding: 1px; background: var(--accent-gradient); border-radius: var(--radius-pill);` обёртку).
- [ ] При скролле (на body или main) добавляется класс `topbarScrolled` через JS-listener или CSS `position: sticky` + `:has` (использовать JS-listener для совместимости).
- [ ] Mobile (≤768px): sidebar `transform: translateX(-100%)` остаётся для совместимости с гамбургером, но в Task 4 на мобиле он будет НЕ показываться вовсе (гамбургер уберём).
- [ ] `bun run build` без ошибок.

**Verify:**
```
cd frontend && bun run build
```
Plus playwright-cli skill snapshot of `/` (desktop).

**Steps:**

- [ ] **Step 1: Полная замена `Layout.module.css`** (sidebar, topbar, layout grid).

Полный файл (заменить целиком):

```css
.layout {
  display: flex;
  min-height: 100vh;
  position: relative;
  z-index: 2;
}

.main {
  flex: 1;
  margin-left: var(--sidebar-width);
  margin-top: var(--topbar-height);
  padding: var(--space-8);
  position: relative;
  z-index: 1;
  min-height: calc(100vh - var(--topbar-height));
  transition: margin-left var(--transition-base);
}

/* ── Sidebar ── */
.sidebar {
  position: fixed;
  top: 0;
  left: 0;
  width: var(--sidebar-width);
  height: 100vh;
  background: var(--bg-surface);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  z-index: 50;
  transition: transform var(--transition-base);
}

.sidebarLogo {
  padding: var(--space-5) var(--space-6);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: var(--space-3);
  height: var(--topbar-height);
}

.sidebarLogoText {
  font-family: var(--font-display);
  font-size: var(--fs-lg);
  font-weight: 600;
  letter-spacing: -0.02em;
  background: var(--accent-gradient);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.sidebarLogoAccent {
  /* Уже идёт градиентом через родителя — оставляем чтобы не ломать разметку. */
}

.sidebarNav {
  flex: 1;
  padding: var(--space-4) var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  overflow-y: auto;
}

.navItem {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: var(--fs-sm);
  font-weight: 500;
  cursor: pointer;
  text-decoration: none;
  transition: background var(--transition-fast), color var(--transition-fast), box-shadow var(--transition-base);
  border: 1px solid transparent;
}

.navItem:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.navItemActive {
  background: var(--bg-hover);
  color: var(--text-primary);
  border-color: var(--border-glow);
  box-shadow: var(--glow-sm);
}

.navItemActive::before {
  content: '';
  position: absolute;
  left: -2px;
  top: 50%;
  transform: translateY(-50%);
  width: 4px;
  height: 16px;
  background: var(--accent-gradient);
  border-radius: var(--radius-pill);
}

.navIcon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}

.navItemDisabled {
  opacity: 0.4;
  cursor: not-allowed;
  pointer-events: none;
}

.comingSoonBadge {
  margin-left: auto;
  font-size: var(--fs-xs);
  font-family: var(--font-mono);
  color: var(--text-muted);
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 1px 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.navDivider {
  height: 1px;
  background: var(--border);
  margin: var(--space-3) var(--space-4);
}

/* ── Topbar ── */
.topbar {
  position: fixed;
  top: 0;
  left: var(--sidebar-width);
  right: 0;
  height: var(--topbar-height);
  background: rgba(11, 11, 20, 0.5);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--space-8);
  z-index: 40;
  transition: left var(--transition-base), background var(--transition-base);
}

.topbarScrolled {
  background: rgba(11, 11, 20, 0.85);
}

.topbarLeft { display: flex; align-items: center; gap: var(--space-3); }
.topbarTitle { font-size: var(--fs-base); font-weight: 600; color: var(--text-primary); }
.topbarRight { display: flex; align-items: center; gap: var(--space-4); }

.userInfo { display: flex; align-items: center; gap: var(--space-3); }

.userAvatar {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-pill);
  background: var(--bg-input);
  border: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--accent-1);
  font-family: var(--font-mono);
  font-size: var(--fs-sm);
  font-weight: 600;
  position: relative;
}

.userAvatarAccent {
  padding: 2px;
  background: var(--accent-gradient);
}
.userAvatarAccent > * {
  border-radius: var(--radius-pill);
  background: var(--bg-base);
}

.userName { font-size: var(--fs-sm); color: var(--text-primary); font-weight: 500; }
.userRole { font-size: var(--fs-xs); color: var(--text-muted); font-family: var(--font-mono); text-transform: uppercase; letter-spacing: 1px; }

.logoutBtn {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-family: var(--font-ui);
  font-size: var(--fs-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}
.logoutBtn:hover {
  border-color: var(--danger);
  color: var(--danger);
  background: var(--danger-bg);
}

.menuBtn {
  display: none;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  cursor: pointer;
  padding: var(--space-2);
  transition: all var(--transition-fast);
}
.menuBtn:hover { color: var(--text-primary); background: var(--bg-hover); }

/* ── Mobile overlay (drawer mode) ── */
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  z-index: 45;
  animation: overlayFadeIn var(--transition-base) ease forwards;
}

@keyframes overlayFadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

/* ── Responsive ── */
@media (max-width: 768px) {
  /* На мобиле sidebar полностью скрываем (его заменит BottomNav в Task 4) */
  .sidebar { display: none; }
  .main {
    margin-left: 0;
    padding: var(--space-4);
    /* Резерв снизу для bottom-nav */
    padding-bottom: calc(var(--bottomnav-height) + var(--space-12));
  }
  .topbar {
    left: 0;
    padding: 0 var(--space-4);
    background: rgba(11, 11, 20, 0.85);
  }
  .menuBtn { display: none; } /* гамбургер больше не нужен */
  .userName, .userRole { display: none; }
}
```

- [ ] **Step 2: Обновить `Topbar.tsx` (scroll-listener для `topbarScrolled`).**

Добавить в `Topbar.tsx`:

```tsx
import { useEffect, useState } from 'react'
// ...
export default function Topbar({ onMenuClick, sidebarOpen }: TopbarProps) {
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <header className={`${styles.topbar} ${scrolled ? styles.topbarScrolled : ''}`}>
      {/* ... остальной jsx без изменений ... */}
    </header>
  )
}
```

(Если в текущем `Topbar.tsx` нет аватара с `accentBorder` — добавляем в Task 15. Сейчас оставить как есть.)

- [ ] **Step 3: Удалить гамбургер из `MainLayout`/`Topbar` для мобайла.**

Поскольку CSS теперь скрывает sidebar на мобиле, гамбургер не нужен. В `Topbar.tsx` оставляем `menuBtn` JSX (тестовая совместимость), но через CSS `display: none` он не показывается. State `sidebarOpen` оставляем — он влиять на десктоп не должен (там `display: flex`). Полностью убираем — НЕ делаем (минимизируем изменения).

Если в `MainLayout.tsx` есть `useEffect` для блокировки скролла при `sidebarOpen` — он останется, но триггериться не будет, потому что на мобиле меню не открыть. Это OK.

- [ ] **Step 4: Type-check + screenshot.**

Run: `cd frontend && bun run build` — без ошибок.

Через playwright-cli skill: открыть `http://localhost:5173/` (запустив `bun run dev` в фоне), сделать snapshot. Проверить визуально: gradient-логотип, стеклянный sidebar, активный пункт с точкой и glow.

- [ ] **Step 5: Commit.**

```bash
git add frontend/src/components/Layout/Layout.module.css frontend/src/components/Layout/Topbar.tsx
git commit -m "feat(ui): glassmorphic sidebar and topbar with gradient logo"
```

---

### Task 4: BottomNav — мобильная пилюля

**Goal:** Создать `BottomNav.tsx` — floating стеклянная пилюля с пунктами навигации, рендерится только на mobile (≤768px), фильтруется по permissions, активная иконка с aurora-glow и анимированной точкой.

**Files:**
- Create: `frontend/src/components/Layout/BottomNav.tsx`
- Modify: `frontend/src/components/Layout/Layout.module.css` (добавить секцию `.bottomNav...`)
- Modify: `frontend/src/components/Layout/MainLayout.tsx` (рендер `<BottomNav />`)

**Acceptance Criteria:**
- [ ] Компонент рендерится только при viewport ≤768px (через CSS `display: none` на десктопе).
- [ ] Floating: 12px от боков и низа, `border-radius` ~28px, стеклянный фон с blur 28px, тень `--shadow-aurora`.
- [ ] До 5 пунктов из permissions (Home всегда; YouTube/Converter/Image — по permissions; в зависимости от роли — Profile или Admin).
- [ ] Active pill: иконка получает `--accent-gradient` через `mask-image`, под иконкой — анимированная пульсирующая точка.
- [ ] Лейбл активного пункта анимированно появляется (max-width transition с 0 → auto), у неактивных лейбл скрыт.
- [ ] `padding-bottom: env(safe-area-inset-bottom)` для iOS.
- [ ] `aria-current="page"` на активном пункте.
- [ ] `bun run build` без ошибок.

**Verify:**
```
cd frontend && bun run build
```
Plus playwright-cli skill snapshot of `/` at viewport 375×812 (iPhone).

**Steps:**

- [ ] **Step 1: Добавить стили в `Layout.module.css` (в конец файла).**

```css
/* ── BottomNav (mobile only) ── */
.bottomNav {
  display: none;
}

@media (max-width: 768px) {
  .bottomNav {
    display: flex;
    position: fixed;
    bottom: calc(var(--space-3) + env(safe-area-inset-bottom));
    left: var(--space-3);
    right: var(--space-3);
    height: var(--bottomnav-height);
    padding: var(--space-2);
    background: rgba(20, 20, 35, 0.7);
    backdrop-filter: blur(28px);
    -webkit-backdrop-filter: blur(28px);
    border: 1px solid var(--border-strong);
    border-radius: 28px;
    box-shadow: var(--shadow-aurora);
    z-index: 60;
    align-items: center;
    justify-content: space-around;
    gap: var(--space-1);
  }

  .bottomNavItem {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-2);
    height: 100%;
    padding: 0 var(--space-2);
    border-radius: var(--radius-md);
    color: var(--text-muted);
    text-decoration: none;
    font-size: var(--fs-xs);
    font-weight: 500;
    transition: color var(--transition-fast), background var(--transition-fast);
    position: relative;
    overflow: hidden;
  }

  .bottomNavItem:hover { color: var(--text-secondary); }

  .bottomNavIcon {
    width: 22px;
    height: 22px;
    flex-shrink: 0;
  }

  .bottomNavLabel {
    max-width: 0;
    opacity: 0;
    overflow: hidden;
    white-space: nowrap;
    transition: max-width var(--transition-base), opacity var(--transition-base);
  }

  .bottomNavItemActive {
    color: var(--text-primary);
    background: var(--bg-hover);
  }

  .bottomNavItemActive .bottomNavLabel {
    max-width: 120px;
    opacity: 1;
  }

  .bottomNavItemActive .bottomNavIcon {
    color: var(--accent-2);
    filter: drop-shadow(0 0 8px var(--accent-glow));
  }

  .bottomNavItemActive::after {
    content: '';
    position: absolute;
    bottom: 4px;
    left: 50%;
    transform: translateX(-50%);
    width: 4px;
    height: 4px;
    border-radius: var(--radius-pill);
    background: var(--accent-gradient);
    animation: pulseGlow 2s ease-in-out infinite;
  }
}
```

- [ ] **Step 2: Создать `BottomNav.tsx`.**

```tsx
import { NavLink } from 'react-router-dom'
import {
  Home,
  Youtube,
  FileBox,
  Image as ImageIcon,
  User as UserIcon,
  Shield,
} from 'lucide-react'
import { useAuth } from '../../stores/authStore'
import styles from './Layout.module.css'

interface NavItemDef {
  to: string
  icon: typeof Home
  label: string
  end?: boolean
}

export default function BottomNav() {
  const { user } = useAuth()
  if (!user) return null

  const isAdmin = user.role === 'admin' || user.role === 'superadmin'

  const items: NavItemDef[] = [{ to: '/', icon: Home, label: 'Главная', end: true }]

  if (user.permissions.youtube) {
    items.push({ to: '/youtube', icon: Youtube, label: 'YouTube' })
  }
  if (user.permissions.converter) {
    items.push({ to: '/converter', icon: FileBox, label: 'Convert' })
  }
  if (user.permissions.image) {
    items.push({ to: '/image', icon: ImageIcon, label: 'Image' })
  }

  // Пятый пункт: профиль для обычных юзеров, админка для admin/superadmin
  if (isAdmin) {
    items.push({ to: '/admin', icon: Shield, label: 'Admin' })
  } else {
    items.push({ to: '/me', icon: UserIcon, label: 'ЛК' })
  }

  // Если получилось >5, оставляем первые 4 + админку/ЛК на 5й позиции
  const display = items.length > 5 ? [...items.slice(0, 4), items[items.length - 1]] : items

  return (
    <nav className={styles.bottomNav} aria-label="Основная навигация">
      {display.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) =>
            `${styles.bottomNavItem} ${isActive ? styles.bottomNavItemActive : ''}`
          }
        >
          {({ isActive }) => (
            <>
              <item.icon className={styles.bottomNavIcon} aria-hidden="true" />
              <span
                className={styles.bottomNavLabel}
                aria-current={isActive ? 'page' : undefined}
              >
                {item.label}
              </span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}
```

- [ ] **Step 3: Подключить `BottomNav` в `MainLayout.tsx`.**

```tsx
import BottomNav from './BottomNav'
// ...
return (
  <>
    <AuroraBackground />
    <StarryBackground />
    <div className={styles.layout}>
      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <Topbar
        onMenuClick={() => setSidebarOpen((prev) => !prev)}
        sidebarOpen={sidebarOpen}
      />
      <main className={styles.main}>
        <Outlet />
      </main>
      <BottomNav />
    </div>
  </>
)
```

- [ ] **Step 4: Type-check + mobile screenshot.**

Run: `cd frontend && bun run build`. Без ошибок.

Через playwright-cli (skill): запустить `bun run dev`, открыть `/` на viewport 375×812, проверить что sidebar не виден, видна стеклянная пилюля внизу с активным пунктом «Главная».

- [ ] **Step 5: Commit.**

```bash
git add frontend/src/components/Layout/BottomNav.tsx frontend/src/components/Layout/Layout.module.css frontend/src/components/Layout/MainLayout.tsx
git commit -m "feat(ui): add floating glass bottom-nav for mobile"
```

---

### Task 5: HomePage — Hero + стеклянные плитки

**Goal:** Переделать `HomePage` в Hero-блок с большим gradient-логотипом, приветствием по имени и стеклянной сеткой плиток модулей с hover-glow.

**Files:**
- Modify: `frontend/src/pages/Home/HomePage.tsx`
- Modify: `frontend/src/pages/Home/Home.module.css` (полная замена)

**Acceptance Criteria:**
- [ ] Hero: логотип «Naturalsk» (Space Grotesk 56–64px desktop / 36–40px mobile) с `background-clip: text` через `--accent-gradient`.
- [ ] Под логотипом: «Привет, {username}» (Inter 18px secondary).
- [ ] Под приветствием: статус доступа («3 из 5 модулей» / «Все модули доступны»).
- [ ] Грид: `repeat(auto-fit, minmax(260px, 1fr))`, gap 20px, max-width 1100px, центрирован.
- [ ] Плитка: стеклянная (`--bg-surface` + blur 20px), border `--border`, radius `--radius-lg`, иконка 44×44 (gradient через `mask-image` на CSS-уровне или просто покрашенная `--accent-2`), заголовок Space Grotesk 20px, описание Inter 14px secondary.
- [ ] Hover плитки: `transform: translateY(-2px)`, border `--border-glow`, shadow `--glow-sm`.
- [ ] Mobile: 1 колонка, плитки горизонтальные (иконка слева, текст справа).
- [ ] `bun run build` без ошибок.

**Verify:**
```
cd frontend && bun run build
```
Plus playwright-cli snapshot of `/` (desktop + mobile).

**Steps:**

- [ ] **Step 1: Полная замена `Home.module.css`.**

```css
.wrapper {
  min-height: calc(100vh - var(--topbar-height) - var(--space-8) * 2);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-12);
  padding-top: 10vh;
}

.hero {
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
}

.logo {
  font-family: var(--font-display);
  font-size: clamp(2.5rem, 8vw, var(--fs-4xl));
  font-weight: 700;
  letter-spacing: -0.03em;
  background: var(--accent-gradient);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  line-height: 1;
}

.greeting {
  font-family: var(--font-ui);
  font-size: var(--fs-lg);
  color: var(--text-secondary);
  font-weight: 500;
}

.statusLine {
  font-family: var(--font-mono);
  font-size: var(--fs-sm);
  color: var(--text-muted);
  letter-spacing: 0.5px;
}

.grid {
  display: grid;
  gap: var(--space-5);
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  width: min(100%, 1100px);
}

.tile {
  background: var(--bg-surface);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  text-decoration: none;
  color: var(--text-primary);
  transition: transform var(--transition-base), border-color var(--transition-base), box-shadow var(--transition-base);
  position: relative;
  overflow: hidden;
}

.tile:hover {
  border-color: var(--border-glow);
  box-shadow: var(--glow-sm);
  transform: translateY(-2px);
}

.tile:hover .tileIcon {
  filter: drop-shadow(0 0 12px var(--accent-glow));
}

.tileIcon {
  width: 44px;
  height: 44px;
  color: var(--accent-2);
  transition: filter var(--transition-base);
}

.tileTitle {
  font-family: var(--font-display);
  font-size: var(--fs-lg);
  font-weight: 600;
  letter-spacing: -0.01em;
}

.tileDesc {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  line-height: 1.5;
}

@media (max-width: 768px) {
  .wrapper { padding-top: 6vh; gap: var(--space-8); }
  .grid { grid-template-columns: 1fr; gap: var(--space-3); }
  .tile {
    flex-direction: row;
    align-items: center;
    padding: var(--space-4);
    gap: var(--space-4);
  }
  .tileIcon { width: 36px; height: 36px; }
  .tileTitle { font-size: var(--fs-base); }
  .tileDesc { font-size: var(--fs-xs); }
}

@media (prefers-reduced-motion: reduce) {
  .tile, .tile:hover .tileIcon { transition: none; }
  .tile:hover { transform: none; }
}
```

- [ ] **Step 2: Переписать `HomePage.tsx`.**

```tsx
import { NavLink } from 'react-router-dom'
import { Youtube, FileBox, Image as ImageIcon, User as UserIcon, Shield } from 'lucide-react'
import { useAuth } from '../../stores/authStore'
import styles from './Home.module.css'

interface Tile {
  to: string
  icon: typeof Youtube
  title: string
  description: string
}

export default function HomePage() {
  const { user } = useAuth()
  if (!user) return null

  const isAdmin = user.role === 'admin' || user.role === 'superadmin'
  const tiles: Tile[] = []

  if (user.permissions.youtube) {
    tiles.push({ to: '/youtube', icon: Youtube, title: 'YouTube Downloader', description: 'Скачивание видео и плейлистов' })
  }
  if (user.permissions.converter) {
    tiles.push({ to: '/converter', icon: FileBox, title: 'File Converter', description: 'Конвертация документов и медиа' })
  }
  if (user.permissions.image) {
    tiles.push({ to: '/image', icon: ImageIcon, title: 'Image Processor', description: 'Удаление фона и водяных знаков' })
  }
  if (isAdmin) {
    tiles.push({ to: '/admin', icon: Shield, title: 'Admin Panel', description: 'Управление пользователями и мониторинг' })
  } else {
    tiles.push({ to: '/me', icon: UserIcon, title: 'Личный кабинет', description: 'Профиль, сессии и безопасность' })
  }

  const totalAvailable = [user.permissions.youtube, user.permissions.converter, user.permissions.image].filter(Boolean).length
  const status = totalAvailable === 3 ? 'Все модули доступны' : `${totalAvailable} из 3 модулей`

  return (
    <div className={styles.wrapper}>
      <div className={styles.hero}>
        <h1 className={styles.logo}>Naturalsk</h1>
        <p className={styles.greeting}>Привет, {user.username}</p>
        <p className={styles.statusLine}>{status}</p>
      </div>

      <div className={styles.grid}>
        {tiles.map((t) => (
          <NavLink key={t.to} to={t.to} className={styles.tile}>
            <t.icon className={styles.tileIcon} aria-hidden="true" />
            <div>
              <div className={styles.tileTitle}>{t.title}</div>
              <div className={styles.tileDesc}>{t.description}</div>
            </div>
          </NavLink>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Type-check + screenshot.**

Run: `cd frontend && bun run build` — без ошибок.

Через playwright-cli: snapshot `/` desktop + mobile (375px). Убедиться: Hero виден, плитки стеклянные, hover-glow работает.

- [ ] **Step 4: Commit.**

```bash
git add frontend/src/pages/Home/
git commit -m "feat(ui): redesign home with hero and glass module tiles"
```

---

### Task 6: Login + ChangePassword — стеклянная карточка

**Goal:** Переделать страницы логина и смены пароля в одиночную стеклянную карточку по центру с gradient-логотипом и aurora-фоном за ней.

**Files:**
- Modify: `frontend/src/pages/Login/LoginPage.tsx`
- Modify: `frontend/src/pages/Login/LoginPage.module.css` (полная замена)
- Modify: `frontend/src/pages/ChangePassword/ChangePasswordPage.tsx`
- Modify: `frontend/src/pages/ChangePassword/ChangePasswordPage.module.css` (полная замена)

**Acceptance Criteria:**
- [ ] На обоих страницах рендерятся `AuroraBackground` + `StarryBackground` (если они не наследуются от `MainLayout` — а они не должны, потому что это публичные routes, не обёрнутые в `MainLayout`).
- [ ] Стеклянная карточка max-width 420px, centered, с blur 20px, border `--border-strong`, radius `--radius-lg`, padding 32px.
- [ ] Логотип Naturalsk в карточке (Space Grotesk 32px) с gradient-fill.
- [ ] Поля и кнопки — пока inline в стилях карточки, в Task 7 будут унифицированы. Использовать токены палитры.
- [ ] Ошибки — inline под полем (иконка `lucide-react/AlertCircle` + красный текст).
- [ ] Mobile: карточка занимает почти всю ширину (margin 16px от краёв).
- [ ] `bun run build` без ошибок.

**Verify:**
```
cd frontend && bun run build
```
Plus playwright-cli snapshot of `/login` (desktop + mobile).

**Steps:**

- [ ] **Step 1: Проверить текущий рендер фона на Login.**

Run: `rg "StarryBackground" frontend/src/pages/`
Expected: Найти, где сейчас фон рендерится. Если в `LoginPage.tsx` сам — просто добавим `AuroraBackground`. Если только в `MainLayout` — добавим оба в Login.

- [ ] **Step 2: Полная замена `LoginPage.module.css`.**

```css
.wrapper {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4);
  position: relative;
  z-index: 2;
}

.card {
  width: 100%;
  max-width: 420px;
  padding: var(--space-8);
  background: var(--bg-elevated);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-aurora);
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.logo {
  font-family: var(--font-display);
  font-size: var(--fs-2xl);
  font-weight: 700;
  letter-spacing: -0.02em;
  background: var(--accent-gradient);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  text-align: center;
  margin-bottom: var(--space-2);
}

.title {
  font-family: var(--font-display);
  font-size: var(--fs-xl);
  font-weight: 600;
  color: var(--text-primary);
  text-align: center;
}

.field {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.label {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  font-weight: 500;
}

.input {
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
  color: var(--text-primary);
  font-family: var(--font-ui);
  font-size: var(--fs-base);
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
  min-height: 44px;
}
.input:focus {
  outline: none;
  border-color: var(--accent-1);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.18);
}

.button {
  background: var(--accent-gradient);
  color: #fff;
  font-family: var(--font-ui);
  font-size: var(--fs-base);
  font-weight: 600;
  border: none;
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-5);
  cursor: pointer;
  transition: filter var(--transition-fast), transform var(--transition-fast), box-shadow var(--transition-base);
  min-height: 44px;
}
.button:hover { filter: saturate(1.1); box-shadow: var(--glow-md); }
.button:active { transform: scale(0.98); }
.button:disabled { opacity: 0.4; cursor: not-allowed; }

.error {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3);
  background: var(--danger-bg);
  border: 1px solid var(--danger);
  border-radius: var(--radius-md);
  color: var(--danger);
  font-size: var(--fs-sm);
}

@media (max-width: 480px) {
  .card { padding: var(--space-6); }
}
```

- [ ] **Step 3: Обновить `LoginPage.tsx`.**

Открыть `frontend/src/pages/Login/LoginPage.tsx`, найти разметку формы и:
- Импортировать `AuroraBackground` и `StarryBackground` если их там нет.
- Обернуть рендер: `<><AuroraBackground /><StarryBackground />...wrapper...</>`.
- Сменить названия классов на новые (`styles.card`, `styles.field`, `styles.label`, `styles.input`, `styles.button`, `styles.error`).
- Добавить заголовок `<h1 className={styles.logo}>Naturalsk</h1>` сверху и подзаголовок.
- Иконку ошибки — через `<AlertCircle size={16} />` из `lucide-react`.

(Точные имена и структуру state/handlers сохранить как есть — только классы и обёртка меняются.)

- [ ] **Step 4: Тот же процесс для `ChangePasswordPage`.**

Скопировать `LoginPage.module.css` стили (или импортировать общие через путь `../Login/LoginPage.module.css` если хочется DRY — но проще скопировать, потому что обе страницы получат UI-kit в Task 7+).

В `ChangePasswordPage.tsx` сделать ту же обёртку.

- [ ] **Step 5: Type-check + screenshot.**

Run: `cd frontend && bun run build` — без ошибок.

Через playwright-cli: snapshot `/login` desktop + mobile, `/change-password`.

- [ ] **Step 6: Commit.**

```bash
git add frontend/src/pages/Login frontend/src/pages/ChangePassword
git commit -m "feat(ui): glass card login and change-password pages"
```

---

## Phase 2 — Profile + UI-kit

### Task 7: UI-kit primitives (Button, Card, Input, DropZone)

**Goal:** Создать переиспользуемые React-компоненты `Button`, `Card`, `Input`, `DropZone` со всеми вариантами из спека (Секция 4 спека). Эти примитивы будут использоваться во всех последующих задачах.

**Files:**
- Create: `frontend/src/components/ui/Button.tsx`
- Create: `frontend/src/components/ui/Button.module.css`
- Create: `frontend/src/components/ui/Card.tsx`
- Create: `frontend/src/components/ui/Card.module.css`
- Create: `frontend/src/components/ui/Input.tsx`
- Create: `frontend/src/components/ui/Input.module.css`
- Create: `frontend/src/components/ui/DropZone.tsx`
- Create: `frontend/src/components/ui/DropZone.module.css`
- Create: `frontend/src/components/ui/index.ts`

**Acceptance Criteria:**
- [ ] `<Button variant="primary|secondary|ghost|danger" size="sm|md|lg" loading? disabled? />` — все варианты visually distinct, touch-target ≥44 на `md`/`lg`.
- [ ] Primary CTA — `--accent-gradient` фон, hover `--glow-md`, active `scale(0.98)`.
- [ ] `<Card variant="glass|elevated" className?>` — glass = `--bg-surface` + blur 20px, elevated = `--bg-elevated` + blur 24px + `--shadow-aurora`.
- [ ] `<Input label error helper {...inputProps}>` — лейбл сверху, `<input>` стеклянный focus-ring, ошибка inline снизу с иконкой.
- [ ] `<DropZone onFiles accept multiple? />` — пунктирная aurora-рамка, animated dash при drag-over, `--accent-glow` пульс.
- [ ] Все компоненты используют `forwardRef` где имеет смысл (Input, Button).
- [ ] `bun run build` без ошибок.

**Verify:**
```
cd frontend && bun run build
```

**Steps:**

- [ ] **Step 1: Создать `Button.module.css`.**

```css
.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  font-family: var(--font-ui);
  font-weight: 600;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: filter var(--transition-fast), transform var(--transition-fast),
              box-shadow var(--transition-base), background var(--transition-base),
              border-color var(--transition-base), color var(--transition-base);
  border: 1px solid transparent;
  white-space: nowrap;
  user-select: none;
  text-decoration: none;
}
.button:disabled { opacity: 0.4; cursor: not-allowed; }
.button:active:not(:disabled) { transform: scale(0.98); }

.sizeSm { font-size: var(--fs-sm); padding: var(--space-2) var(--space-3); min-height: 32px; }
.sizeMd { font-size: var(--fs-base); padding: var(--space-3) var(--space-4); min-height: 44px; }
.sizeLg { font-size: var(--fs-lg); padding: var(--space-4) var(--space-6); min-height: 52px; }

.primary {
  background: var(--accent-gradient);
  color: #fff;
}
.primary:hover:not(:disabled) { filter: saturate(1.1); box-shadow: var(--glow-md); }

.secondary {
  background: var(--bg-surface);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-color: var(--border-strong);
  color: var(--text-primary);
}
.secondary:hover:not(:disabled) { border-color: var(--accent-1); box-shadow: var(--glow-sm); }

.ghost {
  background: transparent;
  color: var(--text-secondary);
}
.ghost:hover:not(:disabled) { color: var(--text-primary); background: var(--bg-hover); }

.danger {
  background: var(--danger);
  color: #fff;
}
.danger:hover:not(:disabled) { background: var(--danger-hover); }

.dangerOutline {
  background: transparent;
  border-color: var(--danger);
  color: var(--danger);
}
.dangerOutline:hover:not(:disabled) { background: var(--danger-bg); }

.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}
```

- [ ] **Step 2: Создать `Button.tsx`.**

```tsx
import { forwardRef, ButtonHTMLAttributes, ReactNode } from 'react'
import styles from './Button.module.css'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'dangerOutline'
type Size = 'sm' | 'md' | 'lg'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
  leftIcon?: ReactNode
  rightIcon?: ReactNode
}

const variantClass: Record<Variant, string> = {
  primary: styles.primary,
  secondary: styles.secondary,
  ghost: styles.ghost,
  danger: styles.danger,
  dangerOutline: styles.dangerOutline,
}

const sizeClass: Record<Size, string> = {
  sm: styles.sizeSm,
  md: styles.sizeMd,
  lg: styles.sizeLg,
}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = 'primary',
      size = 'md',
      loading = false,
      disabled,
      className = '',
      leftIcon,
      rightIcon,
      children,
      ...rest
    },
    ref,
  ) => (
    <button
      ref={ref}
      className={`${styles.button} ${variantClass[variant]} ${sizeClass[size]} ${className}`}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? <span className={styles.spinner} aria-hidden="true" /> : leftIcon}
      {children}
      {rightIcon}
    </button>
  ),
)
Button.displayName = 'Button'
export default Button
```

- [ ] **Step 3: Создать `Card.module.css` + `Card.tsx`.**

```css
.card {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
}
.glass {
  background: var(--bg-surface);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
}
.elevated {
  background: var(--bg-elevated);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  box-shadow: var(--shadow-aurora);
  border-color: var(--border-strong);
}
.interactive {
  transition: transform var(--transition-base), border-color var(--transition-base), box-shadow var(--transition-base);
  cursor: pointer;
}
.interactive:hover {
  transform: translateY(-2px);
  border-color: var(--border-glow);
  box-shadow: var(--glow-sm);
}
@media (prefers-reduced-motion: reduce) {
  .interactive { transition: none; }
  .interactive:hover { transform: none; }
}
```

```tsx
// Card.tsx
import { HTMLAttributes, ReactNode } from 'react'
import styles from './Card.module.css'

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: 'glass' | 'elevated'
  interactive?: boolean
  children?: ReactNode
}

export default function Card({
  variant = 'glass',
  interactive = false,
  className = '',
  children,
  ...rest
}: CardProps) {
  return (
    <div
      className={`${styles.card} ${styles[variant]} ${interactive ? styles.interactive : ''} ${className}`}
      {...rest}
    >
      {children}
    </div>
  )
}
```

- [ ] **Step 4: Создать `Input.module.css` + `Input.tsx`.**

```css
.field { display: flex; flex-direction: column; gap: var(--space-2); }
.label { font-size: var(--fs-sm); color: var(--text-secondary); font-weight: 500; }
.input {
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
  color: var(--text-primary);
  font-family: var(--font-ui);
  font-size: var(--fs-base);
  min-height: 44px;
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
  width: 100%;
}
.input::placeholder { color: var(--text-muted); }
.input:focus {
  outline: none;
  border-color: var(--accent-1);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.18);
}
.inputError {
  border-color: var(--danger);
}
.helper { font-size: var(--fs-xs); color: var(--text-muted); }
.error {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--fs-sm);
  color: var(--danger);
}
```

```tsx
// Input.tsx
import { forwardRef, InputHTMLAttributes, ReactNode } from 'react'
import { AlertCircle } from 'lucide-react'
import styles from './Input.module.css'

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: ReactNode
  error?: ReactNode
  helper?: ReactNode
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, helper, className = '', id, ...rest }, ref) => {
    const inputId = id ?? `input-${Math.random().toString(36).slice(2, 9)}`
    return (
      <div className={styles.field}>
        {label && <label htmlFor={inputId} className={styles.label}>{label}</label>}
        <input
          ref={ref}
          id={inputId}
          className={`${styles.input} ${error ? styles.inputError : ''} ${className}`}
          aria-invalid={!!error}
          {...rest}
        />
        {error ? (
          <span className={styles.error}>
            <AlertCircle size={14} aria-hidden="true" />
            {error}
          </span>
        ) : helper ? (
          <span className={styles.helper}>{helper}</span>
        ) : null}
      </div>
    )
  },
)
Input.displayName = 'Input'
export default Input
```

- [ ] **Step 5: Создать `DropZone.module.css` + `DropZone.tsx`.**

```css
.zone {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  min-height: 180px;
  padding: var(--space-8);
  border: 2px dashed var(--border-strong);
  border-radius: var(--radius-lg);
  background: var(--bg-surface);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  color: var(--text-secondary);
  font-size: var(--fs-sm);
  text-align: center;
  cursor: pointer;
  transition: border-color var(--transition-base), background var(--transition-base), box-shadow var(--transition-base);
}
.zone:hover { border-color: var(--accent-1); }

.zoneActive {
  border-color: var(--accent-2);
  background: rgba(168, 85, 247, 0.06);
  box-shadow: var(--glow-md);
  animation: dashDance 1.6s linear infinite;
}

.zoneIcon { color: var(--accent-1); width: 36px; height: 36px; }
.hint { color: var(--text-muted); font-size: var(--fs-xs); }

@keyframes dashDance {
  to { background-position: 16px 0; }
}

@media (prefers-reduced-motion: reduce) {
  .zoneActive { animation: none; }
}
```

```tsx
// DropZone.tsx
import { useRef, useState, DragEvent, ChangeEvent, ReactNode } from 'react'
import { UploadCloud } from 'lucide-react'
import styles from './DropZone.module.css'

export interface DropZoneProps {
  onFiles: (files: File[]) => void
  accept?: string
  multiple?: boolean
  disabled?: boolean
  label?: ReactNode
  hint?: ReactNode
  className?: string
}

export default function DropZone({
  onFiles,
  accept,
  multiple = true,
  disabled = false,
  label,
  hint,
  className = '',
}: DropZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [active, setActive] = useState(false)

  const handleFiles = (files: FileList | null) => {
    if (!files || disabled) return
    onFiles(Array.from(files))
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setActive(false)
    handleFiles(e.dataTransfer.files)
  }

  const onClick = () => { if (!disabled) inputRef.current?.click() }
  const onChange = (e: ChangeEvent<HTMLInputElement>) => {
    handleFiles(e.target.files)
    e.target.value = ''
  }

  return (
    <div
      className={`${styles.zone} ${active ? styles.zoneActive : ''} ${className}`}
      onDragOver={(e) => { e.preventDefault(); if (!disabled) setActive(true) }}
      onDragLeave={() => setActive(false)}
      onDrop={onDrop}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if ((e.key === 'Enter' || e.key === ' ') && !disabled) onClick() }}
      aria-disabled={disabled}
    >
      <UploadCloud className={styles.zoneIcon} aria-hidden="true" />
      <div>{label ?? 'Перетащите файлы или нажмите для выбора'}</div>
      {hint && <div className={styles.hint}>{hint}</div>}
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        onChange={onChange}
        style={{ display: 'none' }}
        disabled={disabled}
      />
    </div>
  )
}
```

- [ ] **Step 6: Создать `index.ts` (barrel export).**

```ts
export { default as Button } from './Button'
export type { ButtonProps } from './Button'
export { default as Card } from './Card'
export type { CardProps } from './Card'
export { default as Input } from './Input'
export type { InputProps } from './Input'
export { default as DropZone } from './DropZone'
export type { DropZoneProps } from './DropZone'
```

- [ ] **Step 7: Type-check.**

Run: `cd frontend && bun run build` — без ошибок.

- [ ] **Step 8: Commit.**

```bash
git add frontend/src/components/ui/
git commit -m "feat(ui): add UI-kit primitives — Button, Card, Input, DropZone"
```

---

### Task 8: ProfilePage редизайн

**Goal:** Переделать `ProfilePage` и все её под-компоненты (`AvatarUploader`, `ChangePasswordForm`, `ChangeUsernameForm`, `SessionsList`, `UsageBars`, `ProfileTab`) под стеклянные секции с aurora-стилем, использовать UI-kit из Task 7. Двухколоночный layout на desktop, одна колонка на mobile.

**Files:**
- Modify: `frontend/src/pages/Profile/Profile.module.css` (полная замена)
- Modify: `frontend/src/pages/Profile/ProfilePage.tsx`
- Modify: `frontend/src/pages/Profile/ProfileTab.tsx`
- Modify: `frontend/src/pages/Profile/AvatarUploader.tsx` (визуал, поведение не трогаем)
- Modify: `frontend/src/pages/Profile/ChangePasswordForm.tsx`
- Modify: `frontend/src/pages/Profile/ChangeUsernameForm.tsx`
- Modify: `frontend/src/pages/Profile/SessionsList.tsx`
- Modify: `frontend/src/pages/Profile/UsageBars.tsx`

**Acceptance Criteria:**
- [ ] Layout: на ≥1024px — две колонки (аватар-карточка слева 320px фиксированной ширины, остальные секции справа), на <1024px — одна колонка.
- [ ] Аватар-карточка: gradient-обводка вокруг аватара через `padding: 2px; background: var(--accent-gradient)` обёртку.
- [ ] Все секции — `<Card variant="glass">` из UI-kit.
- [ ] Кнопки upload/save/cancel — `<Button>` UI-kit (primary для save, secondary для cancel, dangerOutline для logout/delete).
- [ ] Поля — `<Input>` UI-kit.
- [ ] UsageBars: aurora-gradient заполнение через `background: linear-gradient(90deg, var(--accent-1), var(--accent-2))`. При >80% — gradient становится тёплый (через extra modifier-class `.warning`: `linear-gradient(90deg, var(--warning), var(--danger))`) + мягкий `box-shadow: 0 0 12px var(--danger-bg)`.
- [ ] SessionsList: каждая сессия — мини-карточка (стеклянная, padding 12px), иконка устройства (`Monitor` или `Smartphone` из lucide), время последней активности через `<span className="mono">`, кнопка «Завершить» — `Button variant="dangerOutline" size="sm"`.
- [ ] `bun run build` без ошибок.

**Verify:**
```
cd frontend && bun run build
```
Plus playwright-cli snapshot of `/me` (desktop + mobile).

**Steps:**

- [ ] **Step 1: Полная замена `Profile.module.css`.**

```css
.wrapper {
  max-width: 1100px;
  margin: 0 auto;
  display: grid;
  gap: var(--space-6);
  grid-template-columns: 1fr;
}

@media (min-width: 1024px) {
  .wrapper {
    grid-template-columns: 320px 1fr;
    align-items: start;
  }
}

.avatarCard {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  text-align: center;
}

.avatarRing {
  padding: 3px;
  background: var(--accent-gradient);
  border-radius: var(--radius-pill);
  display: inline-flex;
}

.avatar {
  width: 160px;
  height: 160px;
  border-radius: var(--radius-pill);
  overflow: hidden;
  background: var(--bg-base);
}

.avatarActions {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
  justify-content: center;
}

.username {
  font-family: var(--font-display);
  font-size: var(--fs-xl);
  font-weight: 600;
  color: var(--text-primary);
}

.role {
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 1px;
}

.sections {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.sectionTitle {
  font-family: var(--font-display);
  font-size: var(--fs-lg);
  font-weight: 600;
  margin-bottom: var(--space-4);
  color: var(--text-primary);
}

/* ── Usage bars ── */
.usage {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.usageItem {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.usageHeader {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: var(--fs-sm);
}

.usageLabel { color: var(--text-secondary); }
.usageValue { font-family: var(--font-mono); color: var(--text-primary); }

.usageTrack {
  height: 8px;
  background: var(--bg-input);
  border-radius: var(--radius-pill);
  overflow: hidden;
}

.usageFill {
  height: 100%;
  background: linear-gradient(90deg, var(--accent-1), var(--accent-2));
  border-radius: var(--radius-pill);
  transition: width var(--transition-slow);
}

.usageFillWarning {
  background: linear-gradient(90deg, var(--warning), var(--danger));
  box-shadow: 0 0 12px rgba(248, 113, 113, 0.35);
}

/* ── Sessions ── */
.sessionList {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.sessionItem {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}

.sessionItemCurrent {
  border-color: var(--accent-1);
  box-shadow: var(--glow-sm);
}

.sessionMeta {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.sessionAgent {
  font-size: var(--fs-sm);
  color: var(--text-primary);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sessionTime {
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  color: var(--text-muted);
}
```

- [ ] **Step 2: Обновить `ProfilePage.tsx`.**

Структура:

```tsx
import { Card } from '../../components/ui'
import AvatarUploader from './AvatarUploader'
import UsageBars from './UsageBars'
import SessionsList from './SessionsList'
import ChangePasswordForm from './ChangePasswordForm'
import ChangeUsernameForm from './ChangeUsernameForm'
import { useAuth } from '../../stores/authStore'
import styles from './Profile.module.css'

export default function ProfilePage() {
  const { user } = useAuth()
  if (!user) return null

  return (
    <div className={styles.wrapper}>
      <Card variant="glass" className={styles.avatarCard}>
        <AvatarUploader />
        <div>
          <div className={styles.username}>{user.username}</div>
          <div className={styles.role}>{user.role}</div>
        </div>
      </Card>

      <div className={styles.sections}>
        <Card variant="glass">
          <h2 className={styles.sectionTitle}>Профиль</h2>
          <ChangeUsernameForm />
        </Card>

        <Card variant="glass">
          <h2 className={styles.sectionTitle}>Использование</h2>
          <UsageBars />
        </Card>

        <Card variant="glass">
          <h2 className={styles.sectionTitle}>Активные сессии</h2>
          <SessionsList />
        </Card>

        <Card variant="glass">
          <h2 className={styles.sectionTitle}>Безопасность</h2>
          <ChangePasswordForm />
        </Card>
      </div>
    </div>
  )
}
```

`ProfileTab.tsx` (используется в Admin) — рендерит то же самое или содержательно меньше. Сохраняем существующий API, обновляем только классы и заворачиваем в UI-kit. **Прочитать существующий код перед изменением** и переписать строго в стиле выше — без потери логики.

- [ ] **Step 3: Обновить `AvatarUploader.tsx`.**

В разметке заменить кнопки на `<Button>` из UI-kit:
- «Загрузить» → `<Button variant="primary" size="sm">`
- «Удалить» → `<Button variant="dangerOutline" size="sm">`
- «Crop» / «Cancel» (в модалке кропа) → `<Button variant="primary">` / `<Button variant="ghost">`

Аватар-картинку обернуть в `.avatarRing` → `.avatar` структуру согласно стилю выше.

- [ ] **Step 4: Обновить `ChangeUsernameForm.tsx` и `ChangePasswordForm.tsx`.**

Формы перевести на `<Input>` и `<Button>`. Логика валидации, axios-вызовы, состояния — без изменений.

- [ ] **Step 5: Обновить `UsageBars.tsx`.**

Использовать классы `.usage`, `.usageItem`, `.usageHeader`, `.usageLabel`, `.usageValue`, `.usageTrack`, `.usageFill` (+ `.usageFillWarning` при `percent > 80`).

```tsx
<div className={styles.usageTrack}>
  <div
    className={`${styles.usageFill} ${percent > 80 ? styles.usageFillWarning : ''}`}
    style={{ width: `${Math.min(100, percent)}%` }}
  />
</div>
```

- [ ] **Step 6: Обновить `SessionsList.tsx`.**

Каждый item:

```tsx
<div className={`${styles.sessionItem} ${session.is_current ? styles.sessionItemCurrent : ''}`}>
  <Smartphone size={20} aria-hidden="true" />
  <div className={styles.sessionMeta}>
    <span className={styles.sessionAgent}>{session.user_agent ?? '—'}</span>
    <span className={styles.sessionTime}>{formatTime(session.last_active)}</span>
  </div>
  {!session.is_current && (
    <Button variant="dangerOutline" size="sm" onClick={() => onKill(session.id)}>
      Завершить
    </Button>
  )}
</div>
```

(Имена полей сохранить как в текущем коде — может быть `last_used_at`, `user_agent_raw`, и т.п. **Прочитать существующий компонент перед изменением**.)

- [ ] **Step 7: Type-check + screenshot.**

Run: `cd frontend && bun run build`. Без ошибок.

Через playwright-cli: snapshot `/me` desktop + mobile. Проверить gradient-обводку аватара, стеклянные секции, usage-bars с gradient-заполнением.

- [ ] **Step 8: Commit.**

```bash
git add frontend/src/pages/Profile/
git commit -m "feat(ui): redesign profile page with glass sections and aurora usage bars"
```

---

## Phase 3 — Модули

### Task 9: YouTubePage

**Goal:** Переделать модуль YouTube под Aurora-стиль: стеклянная карточка для URL-инпута и превью, pill-кнопки для опций скачивания, gradient-progress.

**Files:**
- Modify: `frontend/src/pages/YouTube/YouTubePage.tsx`
- Modify: `frontend/src/pages/YouTube/YouTubePage.module.css` (полная замена)
- Modify: `frontend/src/pages/YouTube/VideoCard.tsx`
- Modify: `frontend/src/pages/YouTube/VideoCard.module.css` (полная замена)
- Modify: `frontend/src/pages/YouTube/PlaylistView.tsx`
- Modify: `frontend/src/pages/YouTube/PlaylistView.module.css` (полная замена)
- Modify: `frontend/src/pages/YouTube/DownloadOptions.tsx`
- Modify: `frontend/src/pages/YouTube/DownloadOptions.module.css` (полная замена)
- Modify: `frontend/src/pages/YouTube/DownloadProgress.tsx`
- Modify: `frontend/src/pages/YouTube/DownloadProgress.module.css` (полная замена)

**Acceptance Criteria:**
- [ ] Страница: заголовок «YouTube Downloader» (Space Grotesk 24px) + один основной `<Card variant="glass">` со всем содержимым (URL-input + кнопка «Загрузить» / результат).
- [ ] Input URL — `<Input>` из UI-kit, кнопка «Получить инфо» — `<Button variant="primary">`.
- [ ] VideoCard: thumbnail слева, метаданные справа, стеклянный фон `<Card variant="glass">`, скругление 16px, hover lift.
- [ ] DownloadOptions: pill-кнопки (Button с `borderRadius: 9999px` через override) для разных качеств, активная — primary gradient, остальные — secondary.
- [ ] DownloadProgress: gradient-progress (как в Profile usage-bar), monospace проценты и длительности, состояния (queued/downloading/done/error) — иконки + цвет.
- [ ] PlaylistView: список видео-карточек с компактным режимом.
- [ ] `bun run build` без ошибок. Существующая логика (api-вызовы, state) не меняется.

**Verify:**
```
cd frontend && bun run build
```
Plus playwright-cli snapshot of `/youtube`.

**Steps:**

- [ ] **Step 1: Прочитать существующие компоненты.**

Run:
```
cd frontend/src/pages/YouTube && wc -l *.tsx *.css
cat YouTubePage.tsx VideoCard.tsx DownloadOptions.tsx DownloadProgress.tsx PlaylistView.tsx
```
Понять: какие props, какие state, какие классы, и какая структура JSX. Это нужно чтобы аккуратно поменять только визуал.

- [ ] **Step 2: Полная замена `YouTubePage.module.css`.**

```css
.wrapper {
  max-width: 900px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.title {
  font-family: var(--font-display);
  font-size: var(--fs-2xl);
  font-weight: 600;
  letter-spacing: -0.02em;
  color: var(--text-primary);
}

.subtitle {
  color: var(--text-secondary);
  font-size: var(--fs-sm);
}

.urlForm {
  display: flex;
  gap: var(--space-3);
  align-items: stretch;
}

.urlForm > :first-child { flex: 1; }

@media (max-width: 640px) {
  .urlForm { flex-direction: column; }
}
```

- [ ] **Step 3: Обновить `YouTubePage.tsx`.**

Заменить корневой div на:

```tsx
import { Card, Button, Input } from '../../components/ui'
import styles from './YouTubePage.module.css'

// внутри return:
<div className={styles.wrapper}>
  <div>
    <h1 className={styles.title}>YouTube Downloader</h1>
    <p className={styles.subtitle}>Скачивание видео и плейлистов</p>
  </div>

  <Card variant="glass">
    <form onSubmit={handleSubmit} className={styles.urlForm}>
      <Input
        type="url"
        placeholder="https://youtube.com/watch?v=..."
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        required
      />
      <Button type="submit" loading={loading}>Получить инфо</Button>
    </form>
  </Card>

  {videoInfo && <VideoCard ... />}
  {playlistInfo && <PlaylistView ... />}
  {downloadingItems.map(...)}
</div>
```

(Имена state и handlers — как в текущем коде. См. шаг 1.)

- [ ] **Step 4: Полная замена `VideoCard.module.css`** + обновить компонент.

```css
.card {
  display: flex;
  gap: var(--space-4);
  padding: var(--space-4);
}
.thumbnail {
  width: 200px;
  flex-shrink: 0;
  border-radius: var(--radius-md);
  overflow: hidden;
  aspect-ratio: 16 / 9;
}
.thumbnail img { width: 100%; height: 100%; object-fit: cover; display: block; }
.meta { flex: 1; display: flex; flex-direction: column; gap: var(--space-2); min-width: 0; }
.metaTitle {
  font-family: var(--font-display);
  font-size: var(--fs-lg);
  font-weight: 600;
  color: var(--text-primary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.metaSub { color: var(--text-secondary); font-size: var(--fs-sm); display: flex; gap: var(--space-3); flex-wrap: wrap; }
.metaSub > span { font-family: var(--font-mono); font-size: var(--fs-xs); }

@media (max-width: 640px) {
  .card { flex-direction: column; }
  .thumbnail { width: 100%; }
}
```

В `VideoCard.tsx` обернуть корневой `<div>` в `<Card variant="glass" className={styles.card}>`. Остальное — структура та же.

- [ ] **Step 5: Полная замена `DownloadOptions.module.css`** + компонент.

```css
.options {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.optionPill {
  border-radius: var(--radius-pill) !important;
  padding-left: var(--space-5) !important;
  padding-right: var(--space-5) !important;
}
```

В компоненте использовать `<Button variant={isSelected ? 'primary' : 'secondary'} className={styles.optionPill}>`.

- [ ] **Step 6: Полная замена `DownloadProgress.module.css`** + компонент.

```css
.row {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3);
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}
.header { display: flex; justify-content: space-between; gap: var(--space-3); align-items: center; }
.title { font-size: var(--fs-sm); color: var(--text-primary); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.percent { font-family: var(--font-mono); font-size: var(--fs-xs); color: var(--text-secondary); }
.track { height: 6px; background: var(--bg-base); border-radius: var(--radius-pill); overflow: hidden; }
.fill { height: 100%; background: var(--accent-gradient); border-radius: var(--radius-pill); transition: width var(--transition-base); }
.statusError { color: var(--danger); }
.statusDone { color: var(--success); }
```

В компоненте: статус-иконка через `lucide-react` (`Loader`, `Check`, `XCircle`).

- [ ] **Step 7: PlaylistView — стеклянный список карточек.**

Полная замена `PlaylistView.module.css`:

```css
.list { display: flex; flex-direction: column; gap: var(--space-3); }
.header { display: flex; justify-content: space-between; align-items: center; gap: var(--space-3); }
.title { font-family: var(--font-display); font-size: var(--fs-lg); font-weight: 600; }
.counter { font-family: var(--font-mono); font-size: var(--fs-xs); color: var(--text-muted); }
```

В компоненте — обернуть в `<Card>` каждый item или сразу использовать VideoCard в компактном режиме.

- [ ] **Step 8: Type-check + screenshot.**

Run: `cd frontend && bun run build`. Без ошибок.

Через playwright-cli: snapshot `/youtube`. Если есть рабочий тест-аккаунт — попробовать ввести URL и проверить полный flow.

- [ ] **Step 9: Commit.**

```bash
git add frontend/src/pages/YouTube/
git commit -m "feat(ui): redesign YouTube module with glass cards and aurora progress"
```

---

### Task 10: ConverterPage

**Goal:** Переделать конвертер: использовать `<DropZone>` из UI-kit, стеклянные строки файлов с gradient-progress, pill-кнопки настроек.

**Files:**
- Modify: `frontend/src/pages/Converter/ConverterPage.tsx`
- Modify: `frontend/src/pages/Converter/ConverterPage.module.css` (полная замена)
- Modify: `frontend/src/pages/Converter/FileDropZone.tsx` — упростить, использовать UI-kit `<DropZone>` (или удалить компонент совсем и использовать ui-kit прямо в ConverterPage)
- Delete: `frontend/src/pages/Converter/FileDropZone.module.css` (если компонент удаляется)
- Modify: `frontend/src/pages/Converter/FileItem.tsx`
- Modify: `frontend/src/pages/Converter/FileItem.module.css` (полная замена)
- Modify: `frontend/src/pages/Converter/ConvertSettings.tsx`
- Modify: `frontend/src/pages/Converter/ConvertSettings.module.css` (полная замена)
- Modify: `frontend/src/pages/Converter/ConvertProgress.tsx`
- Modify: `frontend/src/pages/Converter/ConvertProgress.module.css` (полная замена)

**Acceptance Criteria:**
- [ ] Главная стеклянная карточка содержит DropZone сверху + список загруженных файлов + блок настроек + кнопка «Конвертировать».
- [ ] Drop-zone используется из UI-kit (`<DropZone>` из Task 7).
- [ ] FileItem: стеклянная строка, иконка типа файла (по mime), имя файла (truncate), размер (`mono`), кнопка-крестик «убрать».
- [ ] ConvertSettings: target format — radio-pills (как DownloadOptions в YouTube), доп. опции (quality, etc.) — `<Input>`.
- [ ] ConvertProgress: те же gradient-bars что в YouTubePage.
- [ ] `bun run build` без ошибок.

**Verify:**
```
cd frontend && bun run build
```
Plus playwright-cli snapshot of `/converter`.

**Steps:**

- [ ] **Step 1: Прочитать существующие компоненты.**

```
cat frontend/src/pages/Converter/ConverterPage.tsx \
    frontend/src/pages/Converter/FileDropZone.tsx \
    frontend/src/pages/Converter/FileItem.tsx \
    frontend/src/pages/Converter/ConvertSettings.tsx \
    frontend/src/pages/Converter/ConvertProgress.tsx
```

Решить: оставить ли отдельный `FileDropZone` или сразу использовать UI-kit. Если в `FileDropZone` есть специфическая логика (валидация типов, etc.) — оставить как обёртку над `<DropZone>`.

- [ ] **Step 2: Полная замена `ConverterPage.module.css`.**

```css
.wrapper { max-width: 900px; margin: 0 auto; display: flex; flex-direction: column; gap: var(--space-6); }
.title { font-family: var(--font-display); font-size: var(--fs-2xl); font-weight: 600; letter-spacing: -0.02em; }
.subtitle { color: var(--text-secondary); font-size: var(--fs-sm); }
.fileList { display: flex; flex-direction: column; gap: var(--space-2); }
.actionBar { display: flex; justify-content: flex-end; gap: var(--space-3); }
```

- [ ] **Step 3: Обновить `ConverterPage.tsx`.**

```tsx
import { Card, Button, DropZone } from '../../components/ui'
import FileItem from './FileItem'
import ConvertSettings from './ConvertSettings'
// ...
<div className={styles.wrapper}>
  <div>
    <h1 className={styles.title}>File Converter</h1>
    <p className={styles.subtitle}>Конвертация документов и медиа</p>
  </div>

  <Card variant="glass">
    <DropZone
      onFiles={handleAddFiles}
      accept="..."  /* существующее значение */
      multiple
      label="Перетащите файлы сюда или нажмите для выбора"
      hint="Поддерживаемые форматы: …"
    />
    {files.length > 0 && (
      <div className={styles.fileList}>
        {files.map((f) => <FileItem key={f.id} file={f} onRemove={handleRemove} />)}
      </div>
    )}
    {files.length > 0 && <ConvertSettings ... />}
    <div className={styles.actionBar}>
      <Button onClick={handleConvert} disabled={files.length === 0}>Конвертировать</Button>
    </div>
  </Card>
</div>
```

- [ ] **Step 4: Полная замена `FileItem.module.css`.**

```css
.row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}
.icon { color: var(--accent-2); flex-shrink: 0; }
.meta { flex: 1; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.name { font-size: var(--fs-sm); color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.size { font-family: var(--font-mono); font-size: var(--fs-xs); color: var(--text-muted); }
.removeBtn {
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: var(--space-2);
  border-radius: var(--radius-sm);
  transition: color var(--transition-fast), background var(--transition-fast);
}
.removeBtn:hover { color: var(--danger); background: var(--danger-bg); }
```

- [ ] **Step 5: Полная замена `ConvertSettings.module.css`.**

```css
.settings { display: flex; flex-direction: column; gap: var(--space-4); margin-top: var(--space-4); }
.row { display: flex; flex-direction: column; gap: var(--space-2); }
.label { font-size: var(--fs-sm); color: var(--text-secondary); font-weight: 500; }
.options { display: flex; gap: var(--space-2); flex-wrap: wrap; }
.optionPill { border-radius: var(--radius-pill) !important; padding-left: var(--space-5) !important; padding-right: var(--space-5) !important; }
```

В `ConvertSettings.tsx` использовать `<Button>` из UI-kit с `className={styles.optionPill}`.

- [ ] **Step 6: ConvertProgress.module.css** — копия из YouTubePage `DownloadProgress.module.css` (Task 9 Step 6). Компонент аналогичен.

- [ ] **Step 7: Type-check + screenshot.**

Run: `cd frontend && bun run build`. Без ошибок.

Через playwright-cli: snapshot `/converter`.

- [ ] **Step 8: Commit.**

```bash
git add frontend/src/pages/Converter/
git commit -m "feat(ui): redesign converter with shared DropZone and glass file rows"
```

---

### Task 11: ImageProcessorPage

**Goal:** Переделать модуль обработки изображений: стеклянная карточка-каркас, before/after split с aurora-разделителем, progress-bars в общем стиле, обновить тесты.

**Files:**
- Modify: `frontend/src/pages/ImageProcessor/ImageProcessorPage.tsx`
- Modify: `frontend/src/pages/ImageProcessor/ImageProcessorPage.module.css` (полная замена)
- Modify: `frontend/src/pages/ImageProcessor/components/ImageUploader.tsx`
- Modify: `frontend/src/pages/ImageProcessor/components/ImageUploader.module.css` (полная замена)
- Modify: `frontend/src/pages/ImageProcessor/components/BackgroundRemoval.tsx` + `.module.css`
- Modify: `frontend/src/pages/ImageProcessor/components/WatermarkRemoval.tsx` + `.module.css`
- Modify: `frontend/src/pages/ImageProcessor/components/ImageCompare.tsx` + `.module.css`
- Modify: `frontend/src/pages/ImageProcessor/components/ImageProgress.tsx` + `.module.css`
- Modify: `frontend/src/pages/ImageProcessor/components/MaskCanvas.tsx` + `.module.css`
- Modify: `frontend/src/pages/ImageProcessor/components/Thumbnail.tsx` + `.module.css`
- Modify: `frontend/src/pages/ImageProcessor/components/ImageProgress.test.tsx` (если ломаются селекторы CSS Modules)
- Modify: `frontend/src/pages/ImageProcessor/components/Thumbnail.test.tsx` (то же)

**Acceptance Criteria:**
- [ ] Главная карточка `<Card variant="glass">` содержит секции: загрузка → выбор операции (BG removal / Watermark removal) → обработка → результат.
- [ ] ImageUploader использует `<DropZone>` из UI-kit для загрузки.
- [ ] ImageCompare: горизонтальный split-view с aurora-разделителем (псевдо-handle с `--accent-gradient` background, `box-shadow: var(--glow-sm)`).
- [ ] ImageProgress: общие gradient-bars (skeleton-shimmer пока идёт обработка).
- [ ] Thumbnail: стеклянная карточка с аватарной обводкой если selected.
- [ ] MaskCanvas: его UI-controls (brush size, undo, etc.) — `<Button>` из UI-kit.
- [ ] BackgroundRemoval / WatermarkRemoval: pills-кнопки опций (как в YouTube).
- [ ] Существующие тесты `*.test.tsx` проходят (потенциально нужно обновить селекторы classes).
- [ ] `bun run build` и `bun run test:run` без ошибок.

**Verify:**
```
cd frontend && bun run build && bun run test:run
```
Plus playwright-cli snapshot of `/image`.

**Steps:**

- [ ] **Step 1: Прочитать существующие компоненты и тесты.**

```
ls frontend/src/pages/ImageProcessor/components/
cat frontend/src/pages/ImageProcessor/ImageProcessorPage.tsx
cat frontend/src/pages/ImageProcessor/components/ImageProgress.test.tsx
cat frontend/src/pages/ImageProcessor/components/Thumbnail.test.tsx
```

Понять, какие классы используются как селекторы в тестах (`screen.getByText`, `container.querySelector('.something')`). Сохранить такие классы или адаптировать тесты.

- [ ] **Step 2: Полная замена `ImageProcessorPage.module.css`.**

```css
.wrapper { max-width: 1100px; margin: 0 auto; display: flex; flex-direction: column; gap: var(--space-6); }
.title { font-family: var(--font-display); font-size: var(--fs-2xl); font-weight: 600; letter-spacing: -0.02em; }
.subtitle { color: var(--text-secondary); font-size: var(--fs-sm); }
.modeTabs { display: flex; gap: var(--space-2); }
.canvasArea { display: flex; flex-direction: column; gap: var(--space-4); }

@media (min-width: 1024px) {
  .canvasArea { flex-direction: row; align-items: flex-start; }
  .canvasArea > :first-child { flex: 1; }
  .canvasArea > :nth-child(2) { width: 280px; flex-shrink: 0; }
}
```

- [ ] **Step 3: Обновить `ImageProcessorPage.tsx`.**

Заворачиваем разделы в `<Card variant="glass">`. Mode tabs — `<Button variant={mode === 'bg' ? 'primary' : 'secondary'}>` с `className={styles.optionPill}` (если есть в общих) или inline.

- [ ] **Step 4: Полная замена `ImageUploader.module.css`** + использование `<DropZone>`.

В `ImageUploader.tsx`:

```tsx
import { DropZone } from '../../../components/ui'
// ...
<DropZone
  onFiles={(files) => onUpload(files[0])}
  accept="image/*"
  multiple={false}
  label="Загрузите изображение"
/>
```

- [ ] **Step 5: ImageCompare — стеклянный split.**

```css
/* ImageCompare.module.css */
.compare {
  position: relative;
  border-radius: var(--radius-lg);
  overflow: hidden;
  background: var(--bg-input);
  user-select: none;
}
.compare img { width: 100%; display: block; }
.handle {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  background: var(--accent-gradient);
  box-shadow: var(--glow-sm);
  transform: translateX(-50%);
  cursor: ew-resize;
}
.handleKnob {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--accent-gradient);
  box-shadow: var(--glow-md);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 14px;
}
```

В компоненте JSX-структуру оставляем, классы заменяем.

- [ ] **Step 6: ImageProgress — gradient bars.**

Стиль скопировать с YouTubePage `DownloadProgress`. Убедиться что тест `ImageProgress.test.tsx` ещё проходит — если он мокает CSS-классы, то изменение classes имени потенциально ломает его. Прочитать тест и обновить.

- [ ] **Step 7: BackgroundRemoval / WatermarkRemoval / MaskCanvas / Thumbnail.**

Каждый компонент — minimal-touch: классы заменяем на новые, кнопки на `<Button>`, progress на новый стиль. Логика без изменений.

- [ ] **Step 8: Запустить тесты.**

Run:
```
cd frontend && bun run test:run
```

Если тесты падают по селекторам — обновить тесты (поправить `.querySelector('.oldClass')` на новые имена).

- [ ] **Step 9: Type-check + screenshot.**

Run: `cd frontend && bun run build`. Без ошибок.

Через playwright-cli: snapshot `/image`.

- [ ] **Step 10: Commit.**

```bash
git add frontend/src/pages/ImageProcessor/
git commit -m "feat(ui): redesign image processor with glass cards and aurora compare handle"
```

---

## Phase 4 — Admin

### Task 12: Admin layout + segmented switcher

**Goal:** Заменить текущие табы админки на стеклянный segmented switcher (pill-форма с gradient-active), сохранить URL-state (`?tab=...`), на mobile добавить snap-scroll.

**Files:**
- Modify: `frontend/src/pages/Admin/AdminPage.tsx`
- Modify: `frontend/src/pages/Admin/Admin.module.css` (полная замена)

**Acceptance Criteria:**
- [ ] Switcher: стеклянная пилюля (`--bg-surface` + blur), внутри 4 пункта (`Пользователи / Аудит / Мониторинг / Профиль`), активный — `--accent-gradient` фон, остальные — без фона.
- [ ] Видимость пунктов фильтруется по роли: Monitoring видим только superadmin (как сейчас).
- [ ] URL-state не меняется (`?tab=users|audit|monitoring|profile`).
- [ ] Mobile (<640px): pill превращается в горизонтально-скроллящуюся ленту с `scroll-snap`.
- [ ] `bun run build` без ошибок.

**Verify:**
```
cd frontend && bun run build
```
Plus playwright-cli snapshot of `/admin?tab=users` (desktop + mobile).

**Steps:**

- [ ] **Step 1: Полная замена `Admin.module.css`.**

```css
.wrapper {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.title {
  font-family: var(--font-display);
  font-size: var(--fs-2xl);
  font-weight: 600;
  letter-spacing: -0.02em;
}

/* ── Segmented switcher ── */
.switcher {
  display: inline-flex;
  background: var(--bg-surface);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  padding: 4px;
  gap: 4px;
  align-self: flex-start;
}

.switcherTab {
  padding: var(--space-2) var(--space-5);
  background: transparent;
  border: none;
  border-radius: var(--radius-pill);
  color: var(--text-secondary);
  font-family: var(--font-ui);
  font-size: var(--fs-sm);
  font-weight: 500;
  cursor: pointer;
  transition: color var(--transition-fast), background var(--transition-base), box-shadow var(--transition-base);
  white-space: nowrap;
}
.switcherTab:hover { color: var(--text-primary); }

.switcherTabActive {
  background: var(--accent-gradient);
  color: #fff;
  box-shadow: var(--glow-sm);
}

@media (max-width: 640px) {
  .switcher {
    overflow-x: auto;
    scroll-snap-type: x mandatory;
    max-width: 100%;
    align-self: stretch;
  }
  .switcherTab { scroll-snap-align: start; flex-shrink: 0; }
}
```

- [ ] **Step 2: Обновить `AdminPage.tsx`.**

Найти текущий блок с `.tabs` и заменить на:

```tsx
<div className={styles.switcher} role="tablist">
  <button
    role="tab"
    aria-selected={tab === 'users'}
    className={`${styles.switcherTab} ${tab === 'users' ? styles.switcherTabActive : ''}`}
    onClick={() => setTab('users')}
  >
    Пользователи
  </button>
  <button
    role="tab"
    aria-selected={tab === 'audit'}
    className={`${styles.switcherTab} ${tab === 'audit' ? styles.switcherTabActive : ''}`}
    onClick={() => setTab('audit')}
  >
    Аудит
  </button>
  {isSuperadmin && (
    <button
      role="tab"
      aria-selected={tab === 'monitoring'}
      className={`${styles.switcherTab} ${tab === 'monitoring' ? styles.switcherTabActive : ''}`}
      onClick={() => setTab('monitoring')}
    >
      Мониторинг
    </button>
  )}
  <button
    role="tab"
    aria-selected={tab === 'profile'}
    className={`${styles.switcherTab} ${tab === 'profile' ? styles.switcherTabActive : ''}`}
    onClick={() => setTab('profile')}
  >
    Профиль
  </button>
</div>
```

Обернуть весь page в `.wrapper`. Заголовок `<h1 className={styles.title}>Admin Panel</h1>`.

- [ ] **Step 3: Type-check + screenshot.**

Run: `cd frontend && bun run build`. Без ошибок.

Через playwright-cli: snapshot `/admin?tab=users` desktop + mobile.

- [ ] **Step 4: Commit.**

```bash
git add frontend/src/pages/Admin/AdminPage.tsx frontend/src/pages/Admin/Admin.module.css
git commit -m "feat(ui): replace admin tabs with glass segmented switcher"
```

---

### Task 13: UsersTab + admin модалки

**Goal:** Переделать `UsersTab` в стеклянную data-карточку (на mobile — стек карточек), модалки `EditUserModal`, `CreateUserModal`, `ResetPasswordModal`, `ConfirmDeleteModal` — в общем стиле `<Card variant="elevated">` с `<Input>` и `<Button>` UI-kit.

**Files:**
- Modify: `frontend/src/pages/Admin/UsersTab.tsx`
- Modify: `frontend/src/pages/Admin/Admin.module.css` (добавить секцию `.usersTable`, `.userRow`, `.userMobileCard`, etc.)
- Modify: `frontend/src/pages/Admin/EditUserModal.tsx`
- Modify: `frontend/src/pages/Admin/CreateUserModal.tsx`
- Modify: `frontend/src/pages/Admin/ResetPasswordModal.tsx`
- Modify: `frontend/src/pages/Admin/ConfirmDeleteModal.tsx`

**Acceptance Criteria:**
- [ ] UsersTab desktop: data-grid в `<Card variant="glass">`. Колонки: avatar+name, role chip, status (active/disabled/deleted), last_login, actions (edit / reset / kill / delete).
- [ ] UsersTab mobile (<768px): стек стеклянных мини-карточек, метаданные вертикально, actions — overflow menu (или просто все кнопки вертикально).
- [ ] Role chip: стеклянная пилюля с цветом по роли (`--accent-1` для admin, `--accent-3` для superadmin, `--text-muted` для user).
- [ ] Все 4 модалки: backdrop `rgba(11,11,20,0.6)` + 12px blur, контент — `<Card variant="elevated">` с `--shadow-aurora`, anim entrance fade+scale 0.96→1.
- [ ] Поля ввода — `<Input>`, кнопки — `<Button>` (primary для save, ghost/secondary для cancel, danger для destructive).
- [ ] `bun run build` без ошибок.

**Verify:**
```
cd frontend && bun run build
```
Plus playwright-cli snapshot of `/admin?tab=users` (desktop + mobile + open modal).

**Steps:**

- [ ] **Step 1: Прочитать существующие компоненты.**

```
cat frontend/src/pages/Admin/UsersTab.tsx
cat frontend/src/pages/Admin/EditUserModal.tsx
cat frontend/src/pages/Admin/CreateUserModal.tsx
cat frontend/src/pages/Admin/ResetPasswordModal.tsx
cat frontend/src/pages/Admin/ConfirmDeleteModal.tsx
```

- [ ] **Step 2: Дополнить `Admin.module.css`** (добавить в конец файла):

```css
.usersHeader {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.usersHeader h2 {
  font-family: var(--font-display);
  font-size: var(--fs-lg);
  font-weight: 600;
}

.usersTable {
  display: grid;
  grid-template-columns: 1.5fr 1fr 1fr 1fr auto;
  gap: 0;
  border-radius: var(--radius-md);
  overflow: hidden;
  background: var(--bg-input);
}

.userTableHeader {
  display: contents;
}
.userTableHeader > div {
  padding: var(--space-3);
  background: var(--bg-elevated);
  font-size: var(--fs-xs);
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.userRow {
  display: contents;
}
.userRow > div {
  padding: var(--space-3);
  border-top: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.userName {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  font-size: var(--fs-sm);
  color: var(--text-primary);
}

.roleChip {
  display: inline-flex;
  padding: 2px var(--space-3);
  border-radius: var(--radius-pill);
  background: var(--bg-hover);
  border: 1px solid var(--border);
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.roleChipAdmin { color: var(--accent-1); border-color: var(--accent-1); }
.roleChipSuperadmin { color: var(--accent-3); border-color: var(--accent-3); background: rgba(236, 72, 153, 0.08); }

.statusChip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: 2px var(--space-2);
  border-radius: var(--radius-pill);
  font-size: var(--fs-xs);
}
.statusActive { color: var(--success); background: var(--success-bg); }
.statusDisabled { color: var(--warning); background: var(--warning-bg); }
.statusDeleted { color: var(--danger); background: var(--danger-bg); }

.actionGroup {
  display: flex;
  gap: var(--space-2);
  justify-content: flex-end;
}

/* Mobile: cards instead of grid */
@media (max-width: 768px) {
  .usersTable {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    background: transparent;
  }
  .userTableHeader { display: none; }
  .userRow {
    display: block;
    padding: var(--space-4);
    background: var(--bg-input);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
  }
  .userRow > div {
    border-top: none;
    padding: var(--space-1) 0;
  }
  .actionGroup {
    flex-wrap: wrap;
    justify-content: flex-start;
    margin-top: var(--space-2);
  }
}

/* ── Modal ── */
.modalBackdrop {
  position: fixed;
  inset: 0;
  background: rgba(11, 11, 20, 0.6);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4);
  animation: fadeIn var(--transition-base) ease;
}

.modalCard {
  width: 100%;
  max-width: 480px;
  animation: modalEnter var(--transition-base) cubic-bezier(0.16, 1, 0.3, 1);
}

.modalHeader {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-4);
}

.modalTitle {
  font-family: var(--font-display);
  font-size: var(--fs-lg);
  font-weight: 600;
}

.modalActions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
  margin-top: var(--space-5);
}

.modalForm {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

@keyframes modalEnter {
  from { opacity: 0; transform: scale(0.96); }
  to { opacity: 1; transform: scale(1); }
}

@media (prefers-reduced-motion: reduce) {
  .modalCard, .modalBackdrop { animation: none; }
}
```

- [ ] **Step 3: Обновить `UsersTab.tsx`.**

Структура:

```tsx
import { Card, Button } from '../../components/ui'
import styles from './Admin.module.css'

// ...
<Card variant="glass">
  <div className={styles.usersHeader}>
    <h2>Пользователи ({users.length})</h2>
    <Button onClick={() => setCreateOpen(true)}>+ Создать</Button>
  </div>
  <div className={styles.usersTable}>
    <div className={styles.userTableHeader}>
      <div>Пользователь</div>
      <div>Роль</div>
      <div>Статус</div>
      <div>Последний вход</div>
      <div></div>
    </div>
    {users.map((u) => (
      <div className={styles.userRow} key={u.id}>
        <div className={styles.userName}>
          {/* avatar + username */}
        </div>
        <div>
          <span className={`${styles.roleChip} ${u.role === 'admin' ? styles.roleChipAdmin : ''} ${u.role === 'superadmin' ? styles.roleChipSuperadmin : ''}`}>
            {u.role}
          </span>
        </div>
        <div>
          <span className={`${styles.statusChip} ${statusClass(u)}`}>
            {statusLabel(u)}
          </span>
        </div>
        <div>
          <span className="mono">{formatDate(u.last_login_at)}</span>
        </div>
        <div className={styles.actionGroup}>
          <Button size="sm" variant="ghost" onClick={() => onEdit(u)}>Edit</Button>
          <Button size="sm" variant="ghost" onClick={() => onReset(u)}>Reset</Button>
          <Button size="sm" variant="ghost" onClick={() => onKill(u)}>Kill</Button>
          <Button size="sm" variant="dangerOutline" onClick={() => onDelete(u)}>Del</Button>
        </div>
      </div>
    ))}
  </div>
</Card>
```

(Сохранить точные имена state/handlers/полей из существующего компонента.)

- [ ] **Step 4: Обновить 4 модалки.**

Каждая модалка имеет одинаковую структуру:

```tsx
import { Card, Button, Input } from '../../components/ui'
import styles from './Admin.module.css'

export default function EditUserModal({ user, onClose, onSave }: Props) {
  // ... state ...
  return (
    <div className={styles.modalBackdrop} onClick={onClose}>
      <div className={styles.modalCard} onClick={(e) => e.stopPropagation()}>
        <Card variant="elevated">
          <div className={styles.modalHeader}>
            <h3 className={styles.modalTitle}>Редактировать пользователя</h3>
            <Button variant="ghost" size="sm" onClick={onClose} aria-label="Закрыть">✕</Button>
          </div>
          <form onSubmit={handleSubmit} className={styles.modalForm}>
            <Input label="Имя пользователя" value={username} onChange={(e) => setUsername(e.target.value)} />
            {/* остальные поля */}
            <div className={styles.modalActions}>
              <Button variant="ghost" type="button" onClick={onClose}>Отмена</Button>
              <Button type="submit" loading={saving}>Сохранить</Button>
            </div>
          </form>
        </Card>
      </div>
    </div>
  )
}
```

Применить шаблон ко всем 4 модалкам — `EditUserModal`, `CreateUserModal`, `ResetPasswordModal`, `ConfirmDeleteModal`. У `ConfirmDeleteModal` основная кнопка — `<Button variant="danger">`.

- [ ] **Step 5: Type-check + screenshot.**

Run: `cd frontend && bun run build`. Без ошибок.

Через playwright-cli: snapshot `/admin?tab=users` desktop + mobile + открытая `EditUserModal`.

- [ ] **Step 6: Commit.**

```bash
git add frontend/src/pages/Admin/UsersTab.tsx frontend/src/pages/Admin/Admin.module.css frontend/src/pages/Admin/EditUserModal.tsx frontend/src/pages/Admin/CreateUserModal.tsx frontend/src/pages/Admin/ResetPasswordModal.tsx frontend/src/pages/Admin/ConfirmDeleteModal.tsx
git commit -m "feat(ui): redesign admin users tab and modals with glass surfaces"
```

---

### Task 14: AuditLogTab + MonitoringTab

**Goal:** Переделать таб аудита (стеклянные строки лога с цветными chip'ами действий) и мониторинга (стат-карточки с круговыми aurora-индикаторами и sparkline-графиками).

**Files:**
- Modify: `frontend/src/pages/Admin/AuditLogTab.tsx`
- Modify: `frontend/src/pages/Admin/MonitoringTab.tsx`
- Modify: `frontend/src/pages/Admin/Admin.module.css` (добавить секции `.audit*`, `.monitor*`)

**Acceptance Criteria:**
- [ ] Audit: список в `<Card variant="glass">`. Каждая строка: timestamp (mono), actor (username), action chip, ip, краткие details. Цветные chip'ы по типу действия (login=success, logout=muted, delete=danger, reset=warning, etc.).
- [ ] При >100 элементов рендерится через keep-alive виртуализацию или просто `slice(0, 200)` с пагинацией (если её нет — оставить простой рендер, не вводить новых зависимостей).
- [ ] Monitoring: 3 стат-карточки CPU/RAM/Storage с круговыми SVG-индикаторами (aurora-gradient stroke) + одна большая карточка «System» с текстовыми метриками (uptime, version, etc.) + sparkline для CPU/RAM (если данные есть).
- [ ] Кружки SVG: `<svg width="120" height="120">` с двумя `<circle>` (track + filled), filled использует `<defs>` с `<linearGradient>` индиго→магента.
- [ ] `bun run build` без ошибок.

**Verify:**
```
cd frontend && bun run build
```
Plus playwright-cli snapshot of `/admin?tab=audit` and `/admin?tab=monitoring` (только если залогинен superadmin).

**Steps:**

- [ ] **Step 1: Прочитать существующие компоненты.**

```
cat frontend/src/pages/Admin/AuditLogTab.tsx
cat frontend/src/pages/Admin/MonitoringTab.tsx
```

Понять, какие данные доступны (структура `AuditLog`, поля мониторинга).

- [ ] **Step 2: Дополнить `Admin.module.css`** (добавить в конец):

```css
/* ── Audit ── */
.auditList {
  display: flex;
  flex-direction: column;
}

.auditRow {
  display: grid;
  grid-template-columns: 180px 1fr auto auto;
  gap: var(--space-3);
  padding: var(--space-3);
  border-top: 1px solid var(--border);
  font-size: var(--fs-sm);
  align-items: center;
}
.auditRow:first-child { border-top: none; }

.auditTime {
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  color: var(--text-muted);
}

.auditActor { color: var(--text-primary); }

.auditAction {
  display: inline-flex;
  padding: 2px var(--space-3);
  border-radius: var(--radius-pill);
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  text-transform: lowercase;
  letter-spacing: 0.5px;
  background: var(--bg-hover);
  color: var(--text-secondary);
  border: 1px solid var(--border);
  white-space: nowrap;
}
.auditActionSuccess { color: var(--success); border-color: var(--success); background: var(--success-bg); }
.auditActionWarn { color: var(--warning); border-color: var(--warning); background: var(--warning-bg); }
.auditActionDanger { color: var(--danger); border-color: var(--danger); background: var(--danger-bg); }

.auditIp { font-family: var(--font-mono); font-size: var(--fs-xs); color: var(--text-muted); }

@media (max-width: 768px) {
  .auditRow {
    grid-template-columns: 1fr;
    gap: var(--space-1);
  }
}

/* ── Monitoring ── */
.monitorGrid {
  display: grid;
  gap: var(--space-4);
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.monitorTile {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: var(--space-3);
}

.monitorLabel {
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text-muted);
}

.monitorValue {
  font-family: var(--font-display);
  font-size: var(--fs-2xl);
  font-weight: 600;
  color: var(--text-primary);
}

.monitorRing {
  width: 120px;
  height: 120px;
}

.monitorRingTrack {
  fill: none;
  stroke: var(--border);
  stroke-width: 8;
}

.monitorRingFill {
  fill: none;
  stroke: url(#auroraGrad);
  stroke-width: 8;
  stroke-linecap: round;
  transform: rotate(-90deg);
  transform-origin: center;
  transition: stroke-dashoffset var(--transition-slow);
}

.monitorSystem {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--space-2) var(--space-4);
  font-size: var(--fs-sm);
}
.monitorSystemKey { color: var(--text-muted); font-family: var(--font-mono); font-size: var(--fs-xs); text-transform: uppercase; letter-spacing: 0.5px; }
.monitorSystemValue { color: var(--text-primary); font-family: var(--font-mono); font-size: var(--fs-sm); }
```

- [ ] **Step 3: Обновить `AuditLogTab.tsx`.**

```tsx
import { Card } from '../../components/ui'
import styles from './Admin.module.css'

const actionClass = (action: string) => {
  if (action.includes('login') || action.includes('create')) return styles.auditActionSuccess
  if (action.includes('reset') || action.includes('kick')) return styles.auditActionWarn
  if (action.includes('delete') || action.includes('disable')) return styles.auditActionDanger
  return ''
}

// внутри return:
<Card variant="glass">
  <div className={styles.usersHeader}>
    <h2>Аудит</h2>
    {/* кнопка экспорта если есть */}
  </div>
  <div className={styles.auditList}>
    {entries.map((e) => (
      <div className={styles.auditRow} key={e.id}>
        <span className={styles.auditTime}>{formatDate(e.created_at)}</span>
        <span className={styles.auditActor}>{e.actor_username ?? '—'}</span>
        <span className={`${styles.auditAction} ${actionClass(e.action)}`}>{e.action}</span>
        <span className={styles.auditIp}>{e.ip ?? '—'}</span>
      </div>
    ))}
  </div>
</Card>
```

(Имена полей сохранить из текущей реализации.)

- [ ] **Step 4: Обновить `MonitoringTab.tsx`.**

```tsx
import { Card } from '../../components/ui'
import styles from './Admin.module.css'

function CircularGauge({ value, label }: { value: number; label: string }) {
  const radius = 50
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (value / 100) * circumference
  return (
    <div className={styles.monitorTile}>
      <svg className={styles.monitorRing} viewBox="0 0 120 120">
        <defs>
          <linearGradient id="auroraGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#6366F1" />
            <stop offset="50%" stopColor="#A855F7" />
            <stop offset="100%" stopColor="#EC4899" />
          </linearGradient>
        </defs>
        <circle className={styles.monitorRingTrack} cx="60" cy="60" r={radius} />
        <circle
          className={styles.monitorRingFill}
          cx="60"
          cy="60"
          r={radius}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
      </svg>
      <div>
        <div className={styles.monitorValue}>{value.toFixed(0)}%</div>
        <div className={styles.monitorLabel}>{label}</div>
      </div>
    </div>
  )
}

// внутри return:
<div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
  <Card variant="glass">
    <h2 className="...">Ресурсы</h2>
    <div className={styles.monitorGrid}>
      <CircularGauge value={cpu} label="CPU" />
      <CircularGauge value={ram} label="RAM" />
      <CircularGauge value={disk} label="Storage" />
    </div>
  </Card>
  <Card variant="glass">
    <h2>Система</h2>
    <div className={styles.monitorSystem}>
      <span className={styles.monitorSystemKey}>Uptime</span>
      <span className={styles.monitorSystemValue}>{uptime}</span>
      {/* остальные метрики из ответа /admin/system */}
    </div>
  </Card>
</div>
```

(Использовать реальные имена данных из текущего `MonitoringTab` — может быть `stats.cpu_percent`, `stats.memory_percent`, etc.)

- [ ] **Step 5: Type-check + screenshot.**

Run: `cd frontend && bun run build`. Без ошибок.

Через playwright-cli (как superadmin): snapshot `/admin?tab=audit` и `/admin?tab=monitoring`.

- [ ] **Step 6: Commit.**

```bash
git add frontend/src/pages/Admin/AuditLogTab.tsx frontend/src/pages/Admin/MonitoringTab.tsx frontend/src/pages/Admin/Admin.module.css
git commit -m "feat(ui): redesign audit log and monitoring tabs with aurora gauges"
```

---

### Task 15: AvatarImage + финальные штрихи + полная проверка

**Goal:** Добавить опциональный prop `accentBorder` в `AvatarImage` (gradient-обводка), обновить Topbar чтобы использовать этот prop, провести полную ручную проверку всех страниц через playwright-cli, убедиться что reduced-motion работает на всех анимациях.

**Files:**
- Modify: `frontend/src/components/AvatarImage.tsx`
- Modify: `frontend/src/components/AvatarImage.module.css`
- Modify: `frontend/src/components/Layout/Topbar.tsx` (использовать `accentBorder` если у user есть avatar)

**Acceptance Criteria:**
- [ ] `<AvatarImage>` принимает `accentBorder?: boolean`. При `true` рендерится gradient-обводка через `padding: 2px; background: var(--accent-gradient)` обёртку.
- [ ] Topbar и Profile-page при наличии `user.avatar_version > 0` рендерят `<AvatarImage accentBorder>`. Если `version === 0` — без обводки (просто иконка-плейсхолдер).
- [ ] Все 9 страниц (`/login`, `/change-password`, `/`, `/youtube`, `/converter`, `/image`, `/me`, `/admin?tab=*`) визуально проверены через playwright-cli на desktop (1280×800) и mobile (375×812). Снапшоты сохраняются.
- [ ] При тесте с `prefers-reduced-motion: reduce` (через playwright `emulateMedia`) — все фоновые анимации, hover-translate, page-transitions отключены. Visual diff: фон статичный.
- [ ] Все backend и frontend тесты проходят (`cd backend && .venv/bin/python -m pytest -q` + `cd frontend && bun run test:run`).
- [ ] `bun run build` без ошибок.

**Verify:**
```
cd frontend && bun run build && bun run test:run
cd backend && .venv/bin/python -m pytest -q
```

**Steps:**

- [ ] **Step 1: Прочитать существующий `AvatarImage.tsx` и `AvatarImage.module.css`.**

```
cat frontend/src/components/AvatarImage.tsx frontend/src/components/AvatarImage.module.css
```

Понять props и текущую структуру.

- [ ] **Step 2: Обновить `AvatarImage.module.css`.**

Добавить:

```css
.ring {
  display: inline-flex;
  padding: 2px;
  border-radius: var(--radius-pill);
  background: var(--accent-gradient);
}
.ring > * {
  border-radius: var(--radius-pill);
  background: var(--bg-base);
}
```

- [ ] **Step 3: Обновить `AvatarImage.tsx`.**

Добавить prop `accentBorder?: boolean`. Если `true`, обернуть существующее содержимое в `<span className={styles.ring}>...</span>`.

- [ ] **Step 4: Обновить `Topbar.tsx` чтобы использовать новый prop.**

```tsx
{user?.avatar_version && user.avatar_version > 0 ? (
  <AvatarImage userId={user.id} version={user.avatar_version} size={32} accentBorder />
) : (
  <div className={styles.userAvatar}>
    {user?.username?.[0]?.toUpperCase()}
  </div>
)}
```

(Если `Topbar.tsx` уже использует `AvatarImage` — просто добавить prop `accentBorder`.)

- [ ] **Step 5: Аналогично в Profile-page** (Task 8) — `AvatarUploader` или `ProfilePage` рендерит `AvatarImage` с `accentBorder`.

Если изменения уже сделаны в Task 8 без `accentBorder` — обновить сейчас.

- [ ] **Step 6: Финальный аудит через playwright-cli.**

Запустить `bun run dev` (фон). Через playwright-cli (skill):
1. Залогиниться как admin/superadmin.
2. Snapshot всех страниц на desktop 1280×800.
3. Snapshot всех страниц на mobile 375×812.
4. Snapshot с `emulateMedia({ reducedMotion: 'reduce' })` для главной + login.
5. Сохранить ключевые снапшоты в `playwright-cli`-кэше для последующего сравнения.

При обнаружении регрессий (например, кнопка не имеет hover-фидбека, или текст плохо читается на стекле) — фиксить inline в этом же task.

- [ ] **Step 7: Все тесты + build.**

Run:
```
cd /home/meowcode/projects/naturalskweb/frontend && bun run build && bun run test:run
cd /home/meowcode/projects/naturalskweb/backend && .venv/bin/python -m pytest -q
```

Все три команды должны завершаться без ошибок.

- [ ] **Step 8: Commit.**

```bash
git add frontend/src/components/AvatarImage.tsx frontend/src/components/AvatarImage.module.css frontend/src/components/Layout/Topbar.tsx
# плюс любые fixup-изменения с шага 6
git commit -m "feat(ui): aurora avatar border and final polish across pages"
```

---

## Self-Review

### Покрытие спека (раздел → задача)

| Спек | Задачи |
|------|--------|
| §1 Концепция (Indigo Nebula, mesh, aurora-blob, glass) | T1, T2 |
| §2 Архитектура layout (sidebar/topbar/bottom-nav, safe-area) | T3, T4 |
| §3 Дизайн-токены (цвета, типографика, spacing, radii, shadows, transitions) | T1 |
| §4 Компоненты-ядро (Cards, Buttons, Inputs, Sidebar, Topbar, BottomNav, Modals, Toasts, StarryBackground) | T1 (toasts), T2 (starry), T3 (sidebar/topbar), T4 (bottomnav), T7 (Card/Button/Input), T13 (Modals) |
| §5 Страничные адаптации (Home, Login/ChangePassword, Profile, модули, Admin) | T5 (Home), T6 (Login/CP), T8 (Profile), T9–T11 (модули), T12–T14 (Admin) |
| §6 Анимации (длительности, easing, page transitions, reduced motion) | T1 (transitions tokens), T2 (mesh/blob), T13 (modal entrance), T15 (audit) |
| §7 Доступность (focus-ring, aria-current, contrasts, touch targets, reduced motion) | T1 (focus-ring), T3 (aria-current на Sidebar), T4 (aria-current на BottomNav), T15 (audit) |
| §8 Производительность (blur только на видимых, mesh GPU-композит, шрифты swap, без новых зависимостей) | T1 (font-display: swap), T2 (will-change), всё остальное — convention |
| §9 Скоуп изменений | покрыт T1–T15 |
| §10 Поэтапность | 4 фазы соответствуют T1–T6 / T7–T8 / T9–T11 / T12–T14, T15 — финал |
| §11 Anti-patterns | соблюдается через convention в каждой задаче (focus-ring глобально, лейблы, mono для чисел) |

### Placeholder scan

- Нет «TBD»/«TODO»/«implement later» — каждый шаг содержит код или конкретную команду.
- Нет «add appropriate error handling» — задачи не модифицируют логику обработки ошибок.
- Каждая задача имеет конкретные файлы, шаги с CSS/TSX, и явный verify-команду.

### Type consistency

- `Button.tsx` экспортирует `variant: 'primary' | 'secondary' | 'ghost' | 'danger' | 'dangerOutline'`. Используется в T8/T9/T10/T13 — везде применимое значение.
- `Card.tsx` экспортирует `variant: 'glass' | 'elevated'`. T8/T9/T13 используют `glass`; T13 (модалки) использует `elevated`.
- `<DropZone onFiles>` — везде вызывается `(files: File[]) => void`.
- `--accent-gradient`, `--bg-surface`, `--bg-elevated`, `--glow-sm`, etc. — используются согласно определениям из T1.
- Имена nav-icon `Home, Youtube, FileBox, Image as ImageIcon, User as UserIcon, Shield` — одинаковы в `Sidebar.tsx`, `BottomNav.tsx`, `HomePage.tsx`.
- Admin табы: `'users' | 'audit' | 'monitoring' | 'profile'` — согласовано в спеке (§5) и в задаче T12.

### Известные риски

- `backdrop-filter` не поддерживается в старых Safari (<14). Fallback не делаем (целевая аудитория — закрытое приложение, можно требовать современные браузеры). Если потребуется — добавить `-webkit-backdrop-filter` (уже сделано в стилях) и дополнительный `background-color` opacity 0.85 как fallback.
- Mesh-анимация на слабых устройствах может вызывать заметную нагрузку GPU. Полный fallback (статический gradient) описан в спеке §8 как опциональный — добавим только если playwright-cli тест на мобиле покажет деградацию.
- Существующие тесты `ImageProgress.test.tsx` и `Thumbnail.test.tsx` могут потребовать обновления селекторов CSS Modules — это явно отмечено в T11.

---
