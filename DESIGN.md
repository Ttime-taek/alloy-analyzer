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
| `--link` | `#93c5fd` | Links |
| `--accent` | `#60a5fa` | Accent / focus |

## Motion

Respect `prefers-reduced-motion: reduce` (see `index.css`).

## Layout

- **`.app-shell`**: root wrapper; base `font-size: 14px` (see `index.css`).
- **`.app-main-grid`**: two-column main grid; below **720px** width stacks to a single column with tighter gap.

### Touch targets (narrow viewports)

Below **720px**, primary controls use at least **44×44px** (see `index.css` `@media (max-width: 720px)`). The **periodic element** grid (7 columns) uses **`.periodic-element-grid-wrap`** + **`.periodic-element-grid`**: the grid has a **minimum width** so each cell can stay ≥44px wide; if the viewport is narrower, the wrapper **scrolls horizontally** instead of shrinking cells below 44px.

## UX (audit follow-ups)

- API unreachable: amber **API 오프라인** banner (not silent failure).
- Favorites: “불러오는 중…” appears only if the request takes longer than ~420ms.
- Left input column: mode block vs favorites/totals vs periodic table separated with `border-bottom` spacing.
- Empty results: copy points to the **분석** button; temperature cards include one-line hints for solidus / liquidus / peak.

## Dev

Vite dev server proxies `/api`, `/docs`, `/openapi.json` to `http://127.0.0.1:8000`. If the API is down, the dev proxy returns **503** JSON with `offline: true` instead of a raw proxy **500**, so the app can fall back quietly and the console stays cleaner.
