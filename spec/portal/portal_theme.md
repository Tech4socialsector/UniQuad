# Student Portal — Design System Guidelines
**Scope:** SLCM Student Portal (`slcm-bench-v16`). Apply this to every portal page — new builds, edits to existing pages, and anything generated from a reference/design image.

> **How to use this file:** When a reference image is supplied for a new page, follow its *layout and structure* only. Colors and typography always come from this document, not from the reference image — override any color/font shown in the reference with the rules below. All pages must also be fully **responsive** — see §5.

---

## 1. Colors — sourced from `Student Portal Settings`

Colors are **not hardcoded**. They live on the `Student Portal Settings` singleton doctype and are injected once, in `www/student-portal/_base.html`, into a `<style id="sp-custom-vars">` block on `:root`. `public/css/student_portal.css` consumes those variables. New pages that extend `_base.html` get them for free — reference `var(--sp-*)`, never a literal hex.

| CSS variable | Doctype field | Fallback / live value |
|---|---|---|
| `--sp-primary` | `primary_color` | `#920C24` |
| `--sp-primary-dark` | `primary_dark` | `#0a182c` |
| `--sp-primary-light` | `primary_light` | `rgba(18, 42, 74, 0.06)` |
| `--sp-primary-mid` | `primary_mid` | `rgba(18, 42, 74, 0.12)` |
| `--sp-secondary` | `secondary_color` | `#ed0505` (fallback `#85142b`) |
| `--sp-bg` | `background_color` | `#FFFFFF` |
| `--sp-card-bg` / `--sp-card` | `card_background` | `#ffffff` |
| `--sp-nav-bg` / `--sp-sidebar-bg` | `sidebar_theme` | `#FAFAFA` |
| `--sp-nav-text` / `--sp-sidebar-text` / `--sp-sidebar-text-2` | `nav_text_color` | `#920C24` |
| `--sp-success` | `success_color` | `#16a34a` |
| `--sp-warning` | `warning_color` | `#d97706` |
| `--sp-danger` | `danger_color` | `#dc2626` |
| `--sp-info` | `info_color` | `#0369a1` |
| `--sp-grade-color` | `grade_color` | `NULL` live → falls back to `#000000` |
| `--sp-grade-fail` | `grade_fail_color` | `#dc2626` |
| `--sp-att-good` | `att_good_color` | `#15803d` *(field not yet confirmed on the doctype — see §6)* |
| `--sp-att-warn` | `att_warn_color` | `#b45309` *(field not yet confirmed — see §6)* |
| `--sp-att-danger` | `att_danger_color` | `#85142b` *(field not yet confirmed — see §6)* |

**Gap to flag, not silently work around:** `grade_excellent_color`, `grade_good_color`, and `grade_average_color` exist on the doctype and have live values (`#16a34a`, `#0369a1`, `#d97706`), but **none of them are wired into `sp-custom-vars`** — only `grade_color` and `grade_fail_color` are. Any UI that needs excellent/good/average grade coloring cannot get it from a CSS variable today. Don't invent a `--sp-grade-excellent` variable that doesn't exist in `_base.html` — either it needs to be added there first, or that grading logic must be handled another way. Flag this back rather than assuming.

Non-color theme variables also come from this block and should be reused the same way: `--sp-corner-radius`, `--sp-nav-h`, `--sp-sidebar-w`.

**Usage:**
```css
.some-component {
  background: var(--sp-card-bg);
  border-radius: var(--sp-corner-radius);
  color: var(--sp-nav-text);
}
```

---

## 2. Typography

**Font family:** fixed to Merriweather at the CSS-variable level — `--sp-font-family: 'Merriweather', serif;` (not actually doctype-driven despite the field existing; the `_base.html` block hardcodes it, ignoring `sp_settings.font_family`). Use the variable regardless, in case that's fixed later:

```css
font-family: var(--sp-font-family, "Merriweather", serif);
```

**Font weight rule (explicit — non-standard, intentional):**

| Text style | font-weight |
|---|---|
| Bold text | **400** |
| Everything else (regular text) | **300** |

> ⚠️ Reverse of typical convention (usually 400 = regular, 700 = bold). Intentional — do not "correct" it.

The codebase already applies `font-weight: 400 !important` to its bold set — `.sp-brand`, `h1`–`h6`, `.spd-qa-header h2`, `.spd-qa-label`, `.spd-kpi-value`, `.spd-section-name`, `.sp-nav-item.active`. **What's missing:** nothing currently sets the *regular* side to `300` — `body` and non-active `.sp-nav-item` just inherit the browser/font default, which for Merriweather is effectively `400`, so today bold and regular text aren't actually distinguished by weight. New/updated CSS must add the `300` rule explicitly, it won't happen automatically:

```css
body, p, .context-text, .sp-nav-item:not(.active), .sp-breadcrumb {
  font-weight: 300;
}
```

**Font size scale — fixed values, not doctype-driven:**

`--sp-font-size` exists in `sp-custom-vars` but only resolves to `13px/14px/15px` off the doctype's `font_size` select field — too coarse for this spec, and not what the sizes below should be based on. Treat these four as fixed constants layered on top, not derived from `--sp-font-size`:

| Element | Size |
|---|---|
| Headings (page titles, section titles) | `20px` |
| Body / context text | `14px` |
| Sidebar menu items & breadcrumbs | `16px` |
| Badges and similar small labels | `10px` |

### Typography quick reference — mapped to real classes

```css
h1, h2, h3, .sp-page-title, .spd-section-hdr, .spd-section-name, .spd-qa-header h2 {
  font-family: var(--sp-font-family, "Merriweather", serif);
  font-size: 24px;
  font-weight: 400; /* already applied in student_portal.css */
}

body, p, .context-text {
  font-family: var(--sp-font-family, "Merriweather", serif);
  font-size: 18px;
  font-weight: 300; /* needs to be added — see note above */
}

.sp-nav-item, .sp-breadcrumb {
  font-family: var(--sp-font-family, "Merriweather", serif);
  font-size: 21px;
  font-weight: 300;
}
.sp-nav-item.active, .sp-breadcrumb .is-current {
  font-weight: 400; /* .sp-nav-item.active already bold today */
}

.sp-badge, .sp-nav-id-badge, .sp-notif-badge, .sp-tab-badge, .sp-tab-badge-info,
.fee-inv-badge, .sp-inv-badge {
  font-family: var(--sp-font-family, "Merriweather", serif);
  font-size: 16px;
  font-weight: 300;
}
```

---

## 3. Date & Time Formatting

All dates and times displayed on the portal — page content, tables, badges, tooltips, notifications — must use these formats consistently. Do not rely on browser/locale defaults or Frappe's default `dd-mm-yyyy`/24-hour formatting.

| Type | Format | Example |
|---|---|---|
| Date | `DD/MM/YYYY` | `22/09/2026` |
| Time | 12-hour, with `AM`/`PM` | `09:05 AM`, `04:30 PM` |
| Date + time (when shown together) | `DD/MM/YYYY hh:mm AM/PM` | `22/09/2026 04:30 PM` |

- Zero-pad day, month, hour, and minute (`04:05 PM`, not `4:5 PM`).
- Use a space before `AM`/`PM`, uppercase, no periods (`AM`, not `am` or `A.M.`).
- Apply this on both the frontend (JS date formatting / moment-style helpers used in the portal) and anywhere Jinja renders a date/time server-side in `_base.html` or page templates — check for a shared date-format helper/filter already in use before adding a new one (see §7).

---

## 4. Rules for applying this to a reference image

1. Match layout, spacing, structure, and component placement from the image.
2. Ignore any colors shown in the image — use the CSS variables in §1.
3. Ignore any fonts/sizes shown in the image — use the rules in §2.
4. Reuse the existing classes in §5 wherever the reference shows an equivalent component instead of creating new ones.
5. If the image shows an element not covered above, pick the closest matching category and flag "not explicitly specified — used X as closest match" rather than guessing silently.

---

## 5. Existing reusable classes — do not duplicate

**Sidebar / navigation:** `.sp-nav`, `.sp-hamburger`, `.sp-brand`, `.sp-brand-logo`, `.sp-sidebar`, `.sp-sidebar-section`, `.sp-section-items`, `.sp-nav-item` / `.sp-nav-item.active`, `.sp-sidebar-avatar`, `.sp-sidebar-overlay`

**Badges:** `.sp-badge` (base), `.sp-badge-pass`, `.sp-badge-fail`, `.sp-badge-pend`, `.sp-inv-badge`, `.sp-badge-paid`, `.sp-badge-over`, `.sp-nav-id-badge`, `.sp-notif-badge`, `.sp-tab-badge` / `.sp-tab-badge-info`, `.fee-inv-badge` (`.fee-badge-paid`, `.fee-badge-unpaid`, `.fee-badge-overdue`, `.fee-badge-pending`, `.fee-badge-cancelled`)

**Headings:** `.sp-page-title`, `.spd-section-hdr`, `.spd-section-name`, `.spd-qa-header h2`, `.spd-qa-label`, `.spd-kpi-label`, `.spd-kpi-value`

**Breadcrumbs:** confirmed — **none exist**. Introduce `.sp-breadcrumb` (with an `.is-current` modifier for the active page) following the `sp-` naming convention, not a generic `.breadcrumb`.

---

## 6. Responsiveness

Reuse the breakpoints and sidebar behavior already in `student_portal.css` rather than introducing new ones:

| Breakpoint | Effect |
|---|---|
| `max-width: 900px` | Stat grids (`.sp-stat-grid`, `.sp-stats-bar`) collapse to 2–3 columns |
| `max-width: 800px` / `768px` | **Core breakpoint.** Sidebar hides, hamburger appears; dashboards (`.sp-dash-grid`) collapse to 1 column |
| `max-width: 700px` / `640px` | Secondary grids (attendance stats, fees) collapse to 1–2 columns |
| `max-width: 600px` / `480px` | Final mobile step — cards/grids/action panels go to `1fr`, padding reduced |

**Sidebar at ≤768px:** `.sp-hamburger` switches `display: none → flex`; `.sp-sidebar` gets `transform: translateX(-100%)` (pushed offscreen); `.sp-layout` resets `margin-left: 0`. Clicking the hamburger adds `.open` — sidebar slides in (`translateX(0)`) and `.sp-sidebar-overlay.open` shows the backdrop. New pages must plug into this existing pattern, not build a second mobile-nav mechanism.

Other rules: fluid widths (flex/grid, not fixed px) for containers and cards; wide tables scroll horizontally inside their own container rather than breaking layout; images/logos use `max-width: 100%`. The four fixed font sizes in §2 apply at all breakpoints unless a specific reference image clearly calls for a smaller mobile size — flag that case rather than silently shrinking text.

---

## 7. Open items — still to confirm

1. `att_good_color`, `att_warn_color`, `att_danger_color` — referenced in `sp-custom-vars` but not seen in the doctype's Appearance field list or the live-values query; confirm these fields exist and get their live values.
2. Whether `grade_excellent_color` / `grade_good_color` / `grade_average_color` should be added to `sp-custom-vars` (they exist on the doctype but aren't exposed as CSS variables today) — needed before any excellent/good/average grade UI can use them.
3. Where "bold" (400) should extend beyond the current set — table headers, button labels, form field labels aren't in the existing bold list; confirm per-component as they come up rather than assuming.
4. Whether `font_family` and `font_size` doctype fields being effectively ignored (hardcoded to Merriweather / the 3-step scale in `_base.html`) is intended to stay that way, or is a gap to fix separately — out of scope for this guideline either way, just noting it.
5. Whether the portal already has a shared date/time formatting helper (JS util or Jinja filter) in use anywhere, or whether `DD/MM/YYYY` / 12-hour `AM`/`PM` formatting needs to be introduced from scratch and applied consistently across existing pages too.