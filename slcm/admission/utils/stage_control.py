import frappe
from frappe.utils import today as get_today


def get_intake_for_applicant(applicant_doc_or_name):
    """
    Returns intake_type from the applicant's Program.
    Program is the single source of truth.
    Falls back to 'All' if not set.
    """
    if isinstance(applicant_doc_or_name, str):
        program = frappe.db.get_value(
            "Applicant", applicant_doc_or_name, "program"
        )
    else:
        program = getattr(applicant_doc_or_name, "program", None)

    if not program:
        return "All"
    return frappe.db.get_value("Programme", program, "intake_type") or "All"


def get_cycle_stages(admission_cycle, intake_type=None):
    """
    Returns enabled stage rows from Admission Cycle child table.
    Filtered by intake_type (also includes 'All' stages).
    Ordered by sequence ascending.
    Handles both 'sequence' and 'sequence_no' fieldnames.
    """
    cycle_doc = frappe.get_doc("Admission Cycle", admission_cycle)
    stages = []
    for s in cycle_doc.stages:
        if not s.is_enabled:
            continue
        wf = getattr(s, "applicable_workflow", "All") or "All"
        if intake_type and wf not in ("All", intake_type):
            continue
        stages.append(s)

    # Sort by sequence (handle both fieldname variants)
    def get_seq(s):
        return getattr(s, "sequence", None) or getattr(s, "sequence_no", None) or 0

    return sorted(stages, key=get_seq)


def get_current_stage(admission_cycle, intake_type=None):
    """
    Returns the active stage row based on today's date.
    Falls back to first non-locked stage if no dates are set.
    Returns None if no active stage found.
    """
    stages = get_cycle_stages(admission_cycle, intake_type)
    today = get_today()

    # Priority 1: stage whose date window contains today
    for s in stages:
        sd = getattr(s, "start_date", None) or getattr(s, "stage_start_date", None)
        ed = getattr(s, "end_date", None) or getattr(s, "stage_end_date", None)
        if sd and ed:
            if str(sd) <= today <= str(ed):
                return s

    # Priority 2: first non-locked stage in sequence
    for s in stages:
        if not s.is_stage_locked:
            return s

    return None


def can_apply(admission_cycle, intake_type=None):
    """Returns True if Apply Now should be shown/enabled on /admission page."""
    stage = get_current_stage(admission_cycle, intake_type)
    if not stage:
        return False
    return bool(getattr(stage, "allow_application", 0))


def can_edit_application(admission_cycle, intake_type=None):
    """Returns True if Edit button should appear on /nlsat/my-applications."""
    stage = get_current_stage(admission_cycle, intake_type)
    if not stage:
        return False
    return bool(
        getattr(stage, "is_editable", 0) or
        getattr(stage, "allow_applicant_edit", 0)
    )


def get_portal_stage_list(admission_cycle, intake_type=None):
    """
    Returns list of stage dicts for portal display (stage tracker + dashboard).
    Each dict has: stage_name, stage_type, sequence, status, allow_application,
                   allow_applicant_edit, start_date, end_date
    Status values: completed | active | upcoming
    """
    stages = get_cycle_stages(admission_cycle, intake_type)
    current = get_current_stage(admission_cycle, intake_type)
    today = get_today()

    def get_seq(s):
        return getattr(s, "sequence", None) or getattr(s, "sequence_no", None) or 0

    current_seq = get_seq(current) if current else 0
    result = []

    for s in stages:
        seq = get_seq(s)
        sd = str(getattr(s, "start_date", None) or getattr(s, "stage_start_date", None) or "")
        ed = str(getattr(s, "end_date", None) or getattr(s, "stage_end_date", None) or "")

        if sd and ed:
            if today > ed:
                status = "completed"
            elif sd <= today <= ed:
                status = "active"
            else:
                status = "upcoming"
        else:
            if seq < current_seq:
                status = "completed"
            elif seq == current_seq:
                status = "active"
            else:
                status = "upcoming"

        result.append({
            "stage_name":          s.stage_name,
            "stage_type":          getattr(s, "stage_type", "") or "",
            "sequence":            seq,
            "status":              status,
            "allow_application":   bool(getattr(s, "allow_application", 0)),
            "allow_applicant_edit":bool(getattr(s, "is_editable", 0) or
                                        getattr(s, "allow_applicant_edit", 0)),
            "start_date":          sd or None,
            "end_date":            ed or None,
        })

    return result
