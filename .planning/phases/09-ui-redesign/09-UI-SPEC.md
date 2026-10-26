---
phase: 09
slug: ui-redesign
status: approved
shadcn_initialized: false
preset: none
created: 2026-10-26
---

# Phase 09 — UI Design Contract (Stage 6 UI Redesign)

> Visual and interaction contract for Stage 6 Complete UI Redesign for the Local-First PDF Intelligence System.

---

## 1. Design System & Tokens

| Property | Value | Notes |
|----------|-------|-------|
| Tool / Framework | Streamlit Native Components + Centralized CSS Module | Pure Streamlit, no React/Tailwind/Next.js |
| Icon library | Custom Local Monochromatic SVGs (`assets/icons/`) | 0 external network requests, 0 emojis |
| Font Family | `Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif` | Clean sans-serif, system fallbacks |
| Monospace Font | `ui-monospace, "SF Mono", Menlo, Consolas, monospace` | Used exclusively for code, hashes, and technical identifiers |
| Content Column Max-Width | `820px` (centered) | Matches modern AI chat apps (ChatGPT/Claude/Perplexity) |

---

## 2. Spacing Scale

Declared values (multiples of 4px):

| Token | Value | Usage |
|-------|-------|-------|
| `xs` | 4px | Icon gaps, compact badge padding, inline pill gaps |
| `sm` | 8px | Button inline gaps, input inner spacing, micro card padding |
| `md` | 16px | Message content vertical margins, card padding, toolbar gaps |
| `lg` | 24px | Section padding, container gaps |
| `xl` | 32px | Major component spacing, conversation start gap |
| `2xl` | 48px | Empty-state hero vertical padding |
| `3xl` | 64px | Page boundary spacing |

Exceptions: None.

---

## 3. Typography Hierarchy

| Role | Size | Weight | Line Height | Color | Usage |
|------|------|--------|-------------|-------|-------|
| Display | 26px (`1.625rem`) | 600 | 1.25 | `#F4F4F5` | Welcome state heading, major view headers |
| Heading 1 | 20px (`1.25rem`) | 600 | 1.3 | `#F4F4F5` | Workspace titles, summary primary headings |
| Heading 2 | 17px (`1.0625rem`) | 600 | 1.35 | `#F4F4F5` | Section headers, card group titles |
| Body | 15px (`0.9375rem`) | 400 | 1.6 | `#F4F4F5` | Assistant response text, chat conversation body |
| User Message | 14px (`0.875rem`) | 400 | 1.5 | `#F4F4F5` | User query bubbles/containers |
| Label / Meta | 13px (`0.8125rem`) | 500 | 1.4 | `#A1A1AA` | Sidebar titles, stat labels, metadata items |
| Micro / Caption | 12px (`0.75rem`) | 500 | 1.4 | `#71717A` | Citations, status indicators, timestamps, disclaimer |

---

## 4. Color Palette & Contrast Tokens

| Role | Token Name | Hex Value | Contrast Ratio (on `#09090B`) | Usage |
|------|------------|-----------|-------------------------------|-------|
| Background (60%) | `COLOR_BG` | `#09090B` | N/A (base) | App background, root canvas |
| Primary Surface (30%) | `COLOR_SURFACE` | `#111114` | 1.15:1 | Sidebar background, card surfaces, composer background |
| Elevated Surface | `COLOR_ELEVATED` | `#18181D` | 1.3:1 | Popovers, active state cards, user message containers |
| Subtle Borders | `COLOR_BORDER` | `#29292F` | 1.8:1 | 1px dividers, card boundaries, input outlines |
| Primary Accent (10%) | `COLOR_PRIMARY` | `#A78BFA` | 9.4:1 | Primary buttons, active tab highlights, link accents |
| Secondary Accent | `COLOR_SECONDARY` | `#5EEAD4` | 14.2:1 | Local offline healthy engine status, citation badges |
| Primary Text | `COLOR_TEXT_PRIMARY`| `#F4F4F5` | 17.5:1 | Response text, primary labels, headers |
| Muted Text | `COLOR_TEXT_MUTED` | `#A1A1AA` | 7.8:1 | Subtitles, hints, inactive metadata, timestamps |
| Destructive | `COLOR_DANGER` | `#F87171` | 7.2:1 | Error messages, delete confirmations |
| Warning | `COLOR_WARNING` | `#FBBF24` | 11.5:1 | Degraded model warnings, fallback notices |

### Accent Reservation Policy
`#A78BFA` is reserved strictly for:
1. Primary CTA buttons (e.g. New Chat, Send).
2. Active navigation selection indicator.
3. Focused input borders.
4. Active citation expansion highlights.
It is NEVER used as a background wash for entire message cards or large surfaces.

---

## 5. Visual Rules & Iconography Contract

1. **Strict Emoji Ban:** Zero emojis (`🤖`, `📄`, `⚙️`, `📊`, `🔬`, `➕`, `⚠️`, etc.) anywhere in navigation, headers, statuses, buttons, chips, or assistant branding.
2. **Iconography:** Local SVG files bundled in `assets/icons/` only (e.g., `chat.svg`, `document.svg`, `library.svg`, `summarizer.svg`, `settings.svg`, `sparkle.svg`, `upload.svg`, `trash.svg`, `refresh.svg`, `lock.svg`).
3. **No Excessive Effects:** No neon glows, no gradient text, no animated starfields, no transparent blur hacks. Restrained, solid, matte AMOLED surfaces.
4. **No Permanent Debug Panels:** Hardware telemetry and raw scores are kept inside Settings / Diagnostics, not persistent clutter in Chat.
5. **Readable Response Column:** Assistant messages occupy a clean 760–850px centered column with standard typography (like ChatGPT and Claude).

---

## 6. Copywriting Contract

| Element | Copy |
|---------|------|
| Brand Title | `PAPER / INTELLIGENCE` |
| Brand Subtitle | `Local-First PDF Intelligence` |
| Primary New Chat CTA | `New conversation` |
| Welcome Heading | `What would you like to understand?` |
| Welcome Body | `Ask questions, extract data, analyze figures, and verify findings with page-grounded citations. Zero network egress.` |
| Example Prompt 1 | `Summarize the core thesis and key findings of the document in detail.` |
| Example Prompt 2 | `What are the key tables, numbers, and quantitative data reported?` |
| Example Prompt 3 | `Explain the methodology and approach used in this document.` |
| Example Prompt 4 | `What risks, limitations, or open questions are noted?` |
| Composer Placeholder | `Ask a question about the document...` |
| Scope: All Documents | `All Documents ({count})` |
| Scope: Single Document | `{filename} (p. {pages})` |
| Grounded Citation Tag | `{filename} · p. {page}` |
| Auto-Attributed Citation Tag | `{filename} · p. {page} (auto-attributed)` |
| Empty Library Heading | `No documents indexed` |
| Empty Library Body | `Upload a PDF to begin conversational search and summarization.` |
| Destructive Delete Confirm | `Delete document: Permanently remove this document, its vector index, and all cached summaries.` |
| Destructive Purge Confirm | `Purge all data: Permanently delete all indexed documents, SQLite rows, LanceDB vector tables, and cache.` |

---

## 7. Component & Layout Architecture

### A. Sidebar Shell
- **Brand Header:** Brand SVG mark + title `PAPER / INTELLIGENCE` + subtitle `Local-First PDF Intelligence`.
- **Primary CTA:** Full-width `New conversation` button with clean plus/sparkle SVG.
- **Engine Status:** Compact badge `Local: {model_name}` in restrained teal `#5EEAD4` or warning `#FBBF24`.
- **Navigation:** Distinct radio / selector with items `Chat`, `Document Library`, `Summarizer`, `Settings`, `Diagnostics`.
- **Document Management:** Quick document selector + upload expander.
- **Footer:** Minimal version / mode disclaimer (`100% Offline Local Pipeline · Qwen2-VL · LanceDB`).

### B. Chat Layout
- **Empty State:** Centered brand mark + welcome heading + capability description + 4 quick prompt chips.
- **Conversation Stream:** Clean message stream with `st.chat_message("user")` and `st.chat_message("assistant")`.
- **Assistant Message Format:**
  - Standard markdown formatting for prose, bulleted points, numbered lists, and structured tables.
  - Footnote-style clickable citations inline (`[Doc · p. X]`).
  - Evidence drawer (`st.expander("Sources and Evidence ({count})")`) at the bottom of the message turn, strictly separating answer prose from raw retrieved context chunks.
- **Chat Composer:**
  - Native `st.chat_input` pinned to the bottom of the viewport.
  - Context scope indicator displaying current active document or all-documents focus.

### C. Document Library View
- Clean table/card list of indexed documents.
- Search/filter input.
- Metadata details: page count, chunk count, upload time, SHA-256 (compact).
- Individual document delete action with explicit confirmation dialog.
- Danger zone: Purge all documents.

### D. Summarizer View
- Document dropdown selector.
- 5 Profile radio buttons / pills: `Overview`, `Detailed`, `Study Notes`, `Tables & Figures`, `Findings`.
- Markdown summary output container with structured sections and copy action.

### E. Settings & Diagnostics View
- Hardware telemetry: Process RAM RSS (MB) & GPU VRAM utilization gauge.
- Model provider & health diagnostics.
- Privacy & Cloud controls: Cloud mode opt-in switch with mandatory consent dialog.
- Cache management: Clear cache action with confirmation.

---

## 8. Checker Sign-Off

- [x] Dimension 1 Copywriting: PASS (Specific actionable text, 0 generic placeholders)
- [x] Dimension 2 Visuals: PASS (Strict 0 emoji ban, local SVG only, AMOLED matte surfaces)
- [x] Dimension 3 Color: PASS (Explicit 60-30-10 palette with tested contrast ratios)
- [x] Dimension 4 Typography: PASS (15-16px body, 820px max column, monospace only for code)
- [x] Dimension 5 Spacing: PASS (Strict 4px multiple scale)
- [x] Dimension 6 Registry Safety: PASS (Native Streamlit + local assets, zero external calls)

**Approval:** Approved 2026-10-26
