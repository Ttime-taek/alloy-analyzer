# Design tokens — Auto (test7)

Single source of implementation: `frontend/src/index.css` (`:root`). Update both when changing the palette.

## Typography

| Token | Value | Use |
|--------|--------|-----|
| `--font-sans` | `"Pretendard", Pretendard, system-ui, … "Segoe UI", …` | `body`, `frontend/index.html`에서 **Pretendard** 정적 CSS 로드. `.app-shell` 및 `button`/`input`/`select`/`textarea`·전역 폼에 `var(--font-sans)`로 UA **Times/Arial** 혼입 방지 (**FINDING-DR-001**, **FINDING-FONT-MIX**). **SVG `<text>` / `<tspan>`**는 `inherit` + 차트 축 `fontFamily="inherit"`로 셸과 동일 스택. |

## Color (dark)

| Token | Value | Use |
|--------|--------|-----|
| `--bg-page` | `#020617` | Page background |
| `--bg-elevated` | `#0b1220` | Cards, panels |
| `--bg-table-head` | `#0f172a` | Table header |
| `--border-default` | `#1e293b` | Default borders |
| `--border-muted` | `#1f2937` | Subtle borders |
| `--border-accent` | `#334155` | Emphasis borders |
| `--text-primary` | `#e5e7eb` | Main text |
| `--text-secondary` | `#9ca3af` | Secondary |
| `--text-muted` | `#64748b` | Muted |
| `--text-dim` | `#94a3b8` | Dim |
| `--text-soft` | `#cbd5e1` | 표 헤더·보조 라벨 (`App.jsx` 인라인과 공유) |
| `--link` | `#93c5fd` | Links |
| `--accent` | `#60a5fa` | Accent / focus |

## Motion

Respect `prefers-reduced-motion: reduce` (see `index.css`).

## Layout

- **`.app-shell`**: root wrapper; base `font-size: 14px`, `line-height: 1.55` (see `index.css`). 인라인 패딩 **`28px 26px`** (`App.jsx`)으로 페이지 여백 소폭 확대.
- **`.app-main-grid`**: two-column main grid; **`gap: 28px`**; below **720px** width stacks to a single column with tighter gap.

### Touch targets

**Target size:** interactive controls should meet at least **44×44 CSS px** where users tap (WCAG 2.5.5–aligned practice for dense tool UIs).

**Two layers (both apply):**

1. **All viewports — `frontend/src/App.jsx` (inline styles)**  
   Primary actions use explicit **`minHeight: 44`** and comfortable padding (typically **`10px 12px`**) so desktop mouse and touch stay consistent. Many actions use **`TactileButton`** so hover chrome stays consistent. Covered groups include:
   - Mode / report toggles (`ModeButton`, `SmallToggleButton`)
   - Favorites: save / load / delete (조성 A·B), periodic grid cells (A·B)
   - Sync retry, Sn autofill (A·B), per-row **제거**, result panel **접기/펼치기**

2. **Viewports ≤720px — `frontend/src/index.css`**  
   `@media (max-width: 720px)` raises **all** `.app-shell button`, **select** and **text inputs** (except checkboxes/radios) to **`min-height: 44px`**, bumps empty-state step numbers, IMC chips, and tightens safe-area padding.  
   The **periodic element** grid (7 columns) uses **`.periodic-element-grid-wrap`** + **`.periodic-element-grid`**: the grid keeps a **minimum width** so each cell stays ≥44px wide; if the viewport is narrower, the wrapper **scrolls horizontally** instead of shrinking cells below 44px (**FINDING-002**).

### Design review — resolved findings

| ID | Area | Resolution |
|----|------|------------|
| **FINDING-002** | Periodic grid on narrow screens | Horizontal scroll + `min-width` grid + cell `min-width` / `min-height` 44px under `max-width: 720px` (`index.css`). |
| **FINDING-003** | Global base & small controls | `body` font stack / background / color; `input`/`select`/`textarea` base **16px** (iOS zoom); checkbox **16×16px** + accent (`index.css`). |
| **FINDING-004** | Mode & literature toggles | `minHeight: 44` and increased padding on tab / fast–precision controls (`App.jsx`). |
| **FINDING-005** | Favorites + periodic (A·B) | Save / delete / grid buttons aligned to 44px + padding for both compositions (`App.jsx`). |
| **FINDING-006** | Secondary actions | Sync retry, Sn autofill, row remove, result collapse/expand — same 44px + padding (`App.jsx`). |
| **FINDING-FONT-MIX** | SVG `<text>` 기본 글꼴 | `:root --font-sans` + `.app-shell svg` / `text` / `tspan`에 `inherit`·스택 강제 (`index.css`); 리플로우 차트 `App.jsx` 축 라벨 `fontFamily="inherit"`. |
| **FINDING-DR-001** | DOM 샘플에 Times/Arial | Pretendard 우선 스택 + 폼·셸 명시 `font-family` + 위 SVG 규칙 (`index.css`, `index.html`, `App.jsx`). |

### Interaction (tactile hover)

- **`TactileButton`** (`App.jsx`): wraps primary actions with **`tactile-hit`** + inner **`tactile-hit-label`** so `::before` gradients sit under text. **`linkTone`** maps to **`tactile-hit--link`** (e.g. trust / disclosure line).
- **주기율표** (`periodic-cell-btn`): stronger lift + gradient in `index.css`; not doubled with `tactile-hit`.
- **`CollapsibleSection`**: accordion header uses **`tactile-hit`**; panel uses **`role="region"`** + **`aria-controls` / `aria-labelledby`** when expanded.
- **Fine pointer only** (`@media (hover: hover) and (pointer: fine)`): `tactile-hit`, periodic cells, **`.app-shell select`**, **`.app-shell input[type="number"]`**, **`.result-imc-chip`** share hover / active feedback where applicable.
- **`prefers-reduced-motion: reduce`**: interactive hover transforms, filters, and gradient `::before` overlays are suppressed for **`tactile-hit`** (non-periodic) and **periodic** cells (`index.css`).

## UX (audit follow-ups)

- API unreachable: amber **API 오프라인** banner (not silent failure).
- Favorites: “불러오는 중…” appears only if the request takes longer than ~420ms.
- Left input column: mode block vs favorites/totals vs periodic table separated with `border-bottom` spacing.
- Empty results: copy points to the **분석** button; temperature cards include one-line hints for solidus / liquidus / peak.

## Dev

Vite dev server proxies `/api`, `/docs`, `/openapi.json` to `http://127.0.0.1:8000`. If the API is down, the dev proxy returns **503** JSON with `offline: true` instead of a raw proxy **500**, so the app can fall back quietly and the console stays cleaner.

- **Smoke:** from `frontend/`, run **`npm run test`** (Vitest) — verifies the `App` module loads (`src/app.smoke.test.jsx`).
- **Local data (gitignored):** `favorites.json`, `web_favorites.json`, `profile_settings.json` are per-machine. Copy from `*.example.json` in the repo root if you want starter files; the API tolerates missing `web_favorites.json` / `favorites.json` (empty list + migration path).
- **CI:** GitHub Actions (`.github/workflows/ci.yml`) runs Python `regression_check.py` + compile/import checks, and `frontend` `npm ci` / `test` / `build` / `lint`.
- **npm audit (dev):** Vite 5’s bundled `esbuild` may still report a moderate dev-server advisory; clearing it typically requires a **major Vite upgrade** (`npm audit fix --force`) — not applied automatically to avoid breaking the build.

### Design review (gstack browse, Windows)

- **Local URL for agents:** `http://127.0.0.1:8000/` (`api_server.py` serves `frontend/dist`; rebuild with `npm run build` after UI edits).
- **Browse CLI:** gstack ships headless automation as `browse.exe` under `%USERPROFILE%\.cursor\skills\gstack\browse\dist\` after `bun build --compile browse/src/cli.ts --outfile browse/dist/browse`. Repo helper: **`scripts/prep_design_review.ps1`** (compiles if missing, prints steps).
- Full API is optional for layout/contrast passes; start **`python api_server.py`** when flows need live data.
