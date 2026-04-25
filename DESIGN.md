# Design tokens — Auto (test7)

Single source of implementation: `frontend/src/index.css` (`:root`). Update both when changing the palette.

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

- **`.app-shell`**: root wrapper; base `font-size: 14px` (see `index.css`).
- **`.app-main-grid`**: two-column main grid; below **720px** width stacks to a single column with tighter gap.

### Global base (design review)

- **`body`**: `font-family` system stack, `background: var(--bg-page)`, `color: var(--text-primary)` (`index.css`).
- **Form controls**: `input` / `select` / `textarea` use **16px** font size to reduce iOS zoom-on-focus; checkboxes/radios **16×16px** with `accent-color: var(--accent)` (`index.css`).

### Touch targets (two layers)

1. **Narrow viewport (≤720px)** — `index.css` `@media (max-width: 720px)`  
   - **`.app-shell button`**: `min-height: 44px`.  
   - **`.app-shell select`** and **text inputs** (excluding checkbox/radio): `min-height: 44px`.  
   - **IMC chips**, **empty-state step numbers**, **result prose heads**: slightly larger for readability/tap.  
   - **Periodic grid (FINDING-002)**: **`.periodic-element-grid-wrap`** + **`.periodic-element-grid`** — grid **min-width** keeps each cell ≥44px; narrower viewports get **horizontal scroll** instead of shrinking cells. Grid buttons get flex centering and `touch-action: manipulation`.

2. **Composition panel — all breakpoints** — `frontend/src/App.jsx` (design review FINDING-004–006)  
   Explicit **`minHeight: 44`** (typically with **`padding: 10px 12px`**) on: mode / literature toggles (`ModeButton`, `SmallToggleButton`), favorite save & delete (A and B), periodic element cells (A and B inline styles), **동기화 재시도**, **Sn 자동완성** (A/B), per-row **제거**, **분석 결과 접기/펼치기**.  
   This matches **WCAG 2.5.5**-style minimum targets on desktop as well as mobile, while the CSS layer above still reinforces controls inside `.app-shell` on small screens.

## Design review log (implemented)

| ID | Scope | Where |
|----|--------|--------|
| **FINDING-002** | Periodic 7-column grid: min width + horizontal scroll; cell min 44×44 under 720px | `index.css` (`.periodic-element-grid-wrap` / `.periodic-element-grid`) |
| **FINDING-003** | Global typography, page colors, checkbox size, iOS-friendly form font size | `index.css` (`body`, inputs, `:root`) |
| **FINDING-004** | Single/compare mode and fast/precision toggles | `App.jsx` — `ModeButton`, `SmallToggleButton` |
| **FINDING-005** | Favorite save/delete and periodic grid buttons (조성 A / B symmetry) | `App.jsx` |
| **FINDING-006** | 동기화 재시도, Sn autofill, row remove, result panel expand/collapse | `App.jsx` |

**Deferred (optional):** favorite / “원소 추가” / 젖음 온도 `<select>` elements still use compact inline padding on wide viewports; narrow viewports pick up **44px** `min-height` from `.app-shell select` in `index.css`. Align desktop select padding with tokens if a later pass targets full parity.

## UX (audit follow-ups)

- API unreachable: amber **API 오프라인** banner (not silent failure).
- Favorites: “불러오는 중…” appears only if the request takes longer than ~420ms.
- Left input column: mode block vs favorites/totals vs periodic table separated with `border-bottom` spacing.
- Empty results: copy points to the **분석** button; temperature cards include one-line hints for solidus / liquidus / peak.

## Dev

Vite dev server proxies `/api`, `/docs`, `/openapi.json` to `http://127.0.0.1:8000`. If the API is down, the dev proxy returns **503** JSON with `offline: true` instead of a raw proxy **500**, so the app can fall back quietly and the console stays cleaner.
