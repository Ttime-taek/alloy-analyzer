# AI 합금 분석기 — Design Audit Report
Date: 2026-04-10 | Auditor: GStack design-review

---

## First Impression (1440x900 Desktop)

Dark-themed two-panel layout. Left: composition input. Right: analysis results (empty on load). The periodic table grid of element buttons is the dominant visual element and works well as a direct-manipulation metaphor.

**What lands:** dark theme is appropriate for a technical tool; three colored temperature cards (217/221/241C) are an effective at-a-glance result; the tab-style toggle is clear.

**What doesn't:** the UI is extremely small (dominant font: 12px). The layout tries to fit desktop-app density into a browser. The result panel is invisible until after first analysis with no affordance. The "즐겨찾기 불러오는 중..." message appears on every load before any interaction, creating anxiety for new users.

---

## Design System Extraction

### Colors — CRITICAL ISSUE

- Unique hex values in App.jsx: 81
- Total color instances in App.jsx: 314
- CSS custom properties defined in index.css: 12 (NONE used by App.jsx)

81 unique colors, zero token usage. The developer defined --bg-page, --text-primary, etc. in index.css but then hardcoded hex in every inline style. Split-brain design system: tokens that tokenize nothing.

**Top palette (Tailwind slate/blue, embedded in code not tokens):**
- #cbd5e1 x22 (slate-300, primary text)
- #64748b x20 (slate-500, muted)
- #94a3b8 x17 (slate-400, secondary)
- #1f2937 x16 (gray-800, card bg)
- #0f172a x15 (slate-950, deep bg)
- #93c5fd x11 (blue-300, accent)

### Typography — HIGH SEVERITY

- 12px x57 -- dominant body font size
- 11px x19 -- labels and badge text
- 13px x16 -- secondary content
- 15px x4, 18px x2, 28px x1 -- headings

12px as dominant text is below WCAG 2.1 guidance (14px minimum for body). index.css sets 16px on inputs (correct for iOS zoom) but the rest of the type scale is 12px.

### Spacing — MEDIUM SEVERITY

- "4px 6px" x12 -- most common padding
- "6px 8px" x7
- "8px 10px" x6

No spacing scale. Every padding is a bespoke decision. Nothing breathes.

### Border Radius — LOW SEVERITY

6px x18, 8px x11, 999px x8 (pills), 10px x6, 2px x6, 12px x3 -- six different values, no system.

### Architecture — CRITICAL ISSUE

- Inline style props: 245
- CSS classes used by App.jsx: 0
- Component lines: 3,740
- useState declarations: 32

Every style is an inline style object. Making a global change (bump all text from 12px to 13px) requires touching 57 inline declarations individually. This is the root cause of all token drift.

---

## Issue Summary

| ID | Severity | Issue |
|----|----------|-------|
| DESIGN-001 | HIGH | Empty result panel has no workflow affordance |
| DESIGN-002 | HIGH | Favorites loading flicker on every page load |
| DESIGN-003 | HIGH | 12px dominant font is below readable threshold |
| DESIGN-004 | MEDIUM | No progress indicator during analysis |
| DESIGN-005 | MEDIUM | All element buttons look equal, no visual hierarchy |
| DESIGN-006 | LOW | Auto-complete button has no tooltip/explanation |
| DESIGN-007 | MEDIUM | Temperature cards lack comparison context |
| DESIGN-008 | LOW | Mode toggle buttons unclear active state |
| DESIGN-009 | HIGH | /docs link broken (Vite proxy missing) |

---

## Fix Plan (this session)

1. /docs proxy fix (vite.config.mjs) -- 5 min
2. Font size bump 11px->12px, 12px->13px -- 15 min
3. Favorites flicker suppress -- 10 min
4. Analysis progress spinner -- 10 min
5. Empty state visual guide -- 10 min
