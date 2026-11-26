# Timetable Calendar Diagnostic Report

**App:** slcm (slcm-bench-v16)
**Location:** `/home/n_l_s_i_u/frappe-bench/apps/slcm/slcm/`

## 1. File Inventory
The Timetable feature is rendered directly by the Frappe Web view using the following core files:
- **`www/student-portal/timetable.html`**: The Jinja template responsible for rendering the frontend UI (Day, Week, and Month views) and embedding CSS/JS for the calendar grid layout.
- **`www/student-portal/timetable.py`**: The backend Python controller handling the logic for view bounds (day/week/month), querying the `Time Table` DocType, calculating CSS positioning pixels (`top_px`, `height_px`), and assigning colors.
- **`www/student-portal/_base.html`**: The wrapper layout template.
- **`public/css/student_portal.css`**: The global CSS file loaded via `_base.html`.

There are no shadow files or duplicate components; the portal directly relies on these active files.

## 2. Time-Axis Rendering
The time-axis (8:00 AM to 4:00 PM) is constructed using standard block layout rather than CSS Grid rows. 
- **HTML/CSS structure** (`timetable.html`, Lines 184-202):
  ```css
  .tt-time-slot {
    height: 60px;
    border-bottom: 1px solid var(--sp-border);
    position: relative;
    /* ... */
  }
  .tt-time-slot span {
    position: absolute;
    top: -8px;
    right: 8px;
    background: #fff;
    z-index: 5;
  }
  ```
- **Analysis**: Each hour slot is exactly `60px` high with a bottom border representing the grid line. The hour text (e.g., "10:00 AM") is absolute-positioned shifted up (`top: -8px`) with a solid white background (`#fff`) and a `z-index: 5` so it sits *over* its own border without the line striking through the text.

## 3. Event Overlap Handling
- **Logic**: There is **no collision detection or overlap handling** currently implemented.
- **File**: `timetable.py` (Lines 237-250)
- **Analysis**: The script loops over all fetched schedules and strictly calculates their absolute vertical position relative to 8:00 AM (`top_px = ((h - 8) * 60) + m`). If two events occur at the same time, they will receive identical `top_px` values and render directly stacked on top of one another on the Z-axis in the frontend `.tt-day-col`.

## 4. Event Color Source
- **Source**: Dynamic mapping generated in the backend based on `Course Offering`.
- **File**: `timetable.py` (Lines 8-11, 136-138, 265)
- **Analysis**: A hardcoded palette (`_PALETTE`) of 10 Hex colors exists. The controller extracts the user's enrolled `Course Offering` names, sorts them alphabetically, and assigns each one a consistent color from the palette by index.
- **Fallback**: The `color` variable in `schedules_by_day` attempts to pull from the mapped palette first, then falls back to the `color` field on the `Time Table` DocType.

## 5. Tooltip Component
- **Component**: The tooltip is an embedded `.tt-popover` HTML block rendered inside every event card loop (`timetable.html`, Lines 242-283). 
- **Month View**: Yes, the Month view **does** support tooltips. The exact same `.tt-popover` HTML is rendered inside `.month-event.tt-event-card-month` (Lines 476-500).
- **Positioning**: 
  - CSS defaults to `left: calc(100% + 14px)` (opening to the right).
  - Vanilla JS (`timetable.html`, Lines 684-705) checks `getBoundingClientRect().right` on hover. If it clips past `window.innerWidth`, it applies the `.pop-left` class. If it clips past the left edge (e.g. in Day View), it applies `.pop-down` to push it below the event.

## 6. Week View Horizontal Scroll
- **Container Rules**: `timetable.html` (Lines 141-151, 510)
  ```css
  .tt-grid-container { overflow-x: auto; }
  ```
  ```html
  <div class="tt-grid-inner" style="width: 100%; min-width: 800px;">
  ```
- **Analysis**: The grid layout forces `width: 100%`, but imposes a `min-width: 800px`. If the user's viewport (minus sidebar) is narrower than 800px, the `.tt-grid-inner` overflows its parent container, triggering the horizontal scrollbar. If the viewport is larger, it accurately fills the screen without an empty trailing column.

## 7. Month View Cell Content
- **Rendered Fields**: `timetable.html` (Lines 473-503)
- **Analysis**: Inside each `.month-cell`, the event only prints:
  `{{ cls.from_time }} {{ cls.course_name }}`
- The `venue` (room) and `to_time` are hidden inside the `.tt-popover` and are **not** visible at a glance in the month grid layout.
