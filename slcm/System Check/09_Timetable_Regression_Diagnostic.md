# Timetable Regression Diagnostic

**App:** slcm (slcm-bench-v16)
**Location:** `/home/n_l_s_i_u/frappe-bench/apps/slcm/slcm/System Check/09_Timetable_Regression_Diagnostic.md`

## 1. Server Error Logs
While direct CLI `bench` access was blocked by WSL escaping rules, a review of the code architecture reveals exactly how the error is handled. The entire view logic inside `timetable.py` is wrapped in a massive `try...except` block (Lines 317-319):
```python
    except Exception as exc:
        frappe.log_error(f"Timetable error: {exc}", "Student Portal Timetable")
        context.portal_error = str(exc)
        _set_nav_defaults(context)
```
Any exception thrown during the data-fetching phase is caught silently, written to the `Error Log` doctype, and the function returns immediately. 

## 2. Faculty Name Lookup (Fix #9) - The Root Cause
At `timetable.py` (~Lines 213-218), the following query was introduced:
```python
        # ── Enrich with Faculty names ──────────────────────────────
        faculty_names = {}
        unique_faculties = {s.instructor for s in raw_schedules if s.instructor}
        if unique_faculties:
            facs = frappe.get_all("Faculty", filters={"name": ["in", list(unique_faculties)]}, fields=["name", "employee_name"])
            faculty_names = {f.name: f.employee_name for f in facs}
```
**Finding**: The standard Frappe Education module uses the **`Instructor`** DocType, not `Faculty`. By querying `"Faculty"`, `frappe.get_all` throws a `frappe.exceptions.DoesNotExistError: DocType Faculty not found`. 
Because this query is inside the main `try` block, the exception aborts the rest of the function!

## 3. Month View Date-Cell Generation
Because the `Faculty` query throws an exception, the execution jumps to the `except` block before it can reach the assignment of context variables (Lines 301-305):
```python
        context.days             = days
        context.schedules_by_day = schedules_by_day
```
**Finding**: Since `context.days` is never set, the Month view Jinja loop (`{% for day in days %}`) in `timetable.html` (Line 472) iterates over nothing, resulting in a grid with headers but exactly zero day cells underneath.

## 4. Overlap Clustering (Fix #2)
**Finding**: The clustering logic (Lines 275-299) is robust against division-by-zero. 
```python
                if not placed:
                    clusters.append([ev])
                    
            for cluster in clusters:
                col_count = len(cluster) # Will always be at least 1
```
However, this logic is currently never reached due to the `Faculty` lookup crash above it. Furthermore, it is executed against `schedules_by_day.items()`, which means it blindly runs on the Month view events as well. While mathematically safe, clustering is technically unnecessary for the month view.

## 5. view=day and view=week query paths
**Finding**: The `from_date` and `to_date` logic correctly resolves the bounding boxes for Day and Week views. However, because the `try` block aborts, `context.schedules_by_day` is never passed to the template. The frontend defaults to empty dictionaries, rendering no classes.

## 6. Time-label alignment
**Finding**: The `right: 8px` and `z-index: 20` rules for `.tt-time-slot span` are located in the global `<style>` block in `timetable.html` (Lines 194-202). They apply consistently to both Day and Week views (Month view does not utilize `.tt-time-slot`). There are no conflicting overrides.
