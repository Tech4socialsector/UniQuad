import frappe
import re
from frappe.model.document import Document
from frappe.utils import now_datetime
from .merit_service import generate_merit_for_level


class MeritGeneration(Document):

    def autoname(self):
        from frappe.model.naming import make_autoname
        if not self.admission_cycle or not self.campus:
            frappe.throw("Admission Cycle and Campus are required for naming.")

        # Use codes instead of names to keep it short
        cycle_code = frappe.db.get_value("Admission Cycle", self.admission_cycle, "cycle_code") or self.admission_cycle
        campus_code = frappe.db.get_value("Campus", self.campus, "campus_code") or self.campus
        
        cycle = cycle_code.replace(" ", "").upper()
        campus = campus_code.replace(" ", "").upper()
        level = (self.generation_type or "ALL").replace(" ", "").upper()
        
        if self.program:
            program_code = frappe.db.get_value("Programme", self.program, "program_code") or self.program
            # Allow: - . , ( ) along with Alphanumeric
            prog = re.sub(r'[^A-Z0-9\-\.\,\(\)]', '', program_code.replace(" ", "").upper())
            # Use ignore_validate=True to allow parentheses and commas in naming series prefix
            self.name = make_autoname(f"MG-{cycle}-{campus}-{prog}-.####", ignore_validate=True)
        else:
            self.name = make_autoname(f"MG-{cycle}-{campus}-{level}-.####", ignore_validate=True)

    @frappe.whitelist()
    def clear_generation_progress(self):
        cache_key = f"merit_generation_{self.admission_cycle}_{self.campus}_{self.generation_type}_{self.program or ''}".replace(" ", "_")
        frappe.cache().delete_value(cache_key)
        frappe.cache().set_value(cache_key, {
            "percent": 0,
            "status": "In Progress",
            "description": "Starting merit generation...",
            "current": 0,
            "total": 100
        }, expires_in_sec=300)

    @frappe.whitelist()
    def trigger_generation(self):
        """
        Triggers merit list generation for the selected Program Level.
        """
        self.clear_generation_progress()
        program_level = self.generation_type
        if not program_level:
            frappe.throw("Please select a Program Level (UG / PG / PhD) before generating.")

        # 1. Check if applicants exist for this program level/program
        check_filters = {
            "cycle": self.admission_cycle,
            "campus": self.campus,
            "level": program_level
        }
        
        program_cond = ""
        if self.program:
            program_cond = " AND etsa.program = %(program)s "
            check_filters["program"] = self.program

        applicants = frappe.db.sql(f"""
            SELECT etsa.name 
            FROM `tabEntrance Test Seat Allocation` etsa
            LEFT JOIN `tabProgramme` p ON etsa.program = p.name
            WHERE etsa.admission_cycle = %(cycle)s
              AND (etsa.program_level = %(level)s OR p.level_of_study = %(level)s)
              AND etsa.campus = %(campus)s
              AND etsa.entrance_test_status = 'Attended'
              AND etsa.result_status = 'Pass'
              AND IFNULL(etsa.is_international_applicant, 0) = 0
              {program_cond}
            LIMIT 1
        """, check_filters, as_dict=True)

        if not applicants:
            prog_msg = f" and Program '{self.program}'" if self.program else ""
            frappe.throw(
                f"No applicants found for Program Level '{program_level}'{prog_msg}, "
                f"Campus '{self.campus}' and Admission Cycle '{self.admission_cycle}'.",
                title="No Applicants Found"
            )

        # 3. Check if ANY Published Merit List already exists
        existing_published_filters = {
            "admission_cycle": self.admission_cycle,
            "campus": self.campus,
            "program_level": program_level,
            "status": "Published"
        }
        if self.program:
            existing_published_filters["program"] = self.program

        existing_published = frappe.db.get_value(
            "Merit List",
            existing_published_filters,
            ["name", "generated_on"],
            as_dict=True
        )
        if existing_published:
            self.status = "Completed"
            self.generated_on = existing_published.generated_on
            self.save()
            prog_msg = f" for {self.program}" if self.program else ""
            frappe.msgprint(
                f"The Merit List '{existing_published.name}'{prog_msg} is already published. "
                f"Generation skipped. "
                f"To make changes or regenerate the list, you must first unpublish it. "
                f"<a href='/app/merit-list/{existing_published.name}'><b>View Merit List</b></a>.",
                title="Merit List Published",
                indicator="orange"
            )
            return {"success": False, "skipped": True}

        # 4. All validations passed — enqueue background job
        self.status = "In Progress"
        self.save()
        frappe.db.commit()

        mode = (frappe.conf.get("slcm_merit_generation_mode") or "sync").lower()

        # In production, background workers/redis may be misconfigured. To avoid a stuck
        # 'In Progress' state, allow a synchronous fallback via site_config.
        if mode == "sync":
            try:
                run_generation_main(self.name)
                self.reload()
            except Exception as e:
                frappe.msgprint(
                    f"Merit generation for {program_level} failed: {str(e)}",
                    indicator="red"
                )
                return {"success": False, "error": str(e)}
            return {"success": True}

        try:
            frappe.enqueue(
                "slcm.admission.doctype.merit_generation.merit_generation.run_generation",
                docname=self.name,
                now=frappe.flags.in_test,
                queue="short",
                enqueue_after_commit=True
            )

            frappe.msgprint(
                f"Merit generation for {program_level} started in the background. "
                f"Please check back in a few moments."
            )
            return {"success": True, "async": True}
        except Exception:
            # If enqueue fails (redis/worker issues), run inline so hosted setups still work.
            try:
                run_generation_main(self.name)
                self.reload()
            except Exception as e:
                frappe.msgprint(
                    f"Merit generation for {program_level} failed: {str(e)}",
                    indicator="red"
                )
                return {"success": False, "error": str(e)}
            return {"success": True}

def run_generation(docname):
    """
    Background worker function (wrapper for run_generation_main).
    """
    try:
        run_generation_main(docname)
    except Exception:
        # Traceback is already logged in run_generation_main
        pass


def run_generation_main(docname):
    """
    Core generation logic. Phase 1 (Part A Ranking) is triggered here
    and the results are pushed to the Shortlisting Merit List doctype.
    """
    doc = frappe.get_doc("Merit Generation", docname)
    program_level = doc.generation_type

    try:
        # Phase 1 is ALWAYS the first step in this workflow
        # We don't save the Merit List record here, it's just a data container for Phase 1.
        merit_list_doc = generate_merit_for_level(
            doc.admission_cycle, 
            doc.campus, 
            program_level, 
            program=doc.program,
            processing_stage="Part A Ranking",
            save=False
        )

        # Soft-archive any existing active Shortlisting Merit List as Superseded before creating new list
        sp_filters = {
            "admission_cycle": doc.admission_cycle,
            "campus": doc.campus,
            "program_level": program_level,
            "status": ["!=", "Superseded"]
        }
        if doc.program:
            sp_filters["program"] = doc.program
            
        sp_name = frappe.db.get_value("Shortlisting Merit List", sp_filters, "name")
        if sp_name:
            existing_sp = frappe.get_doc("Shortlisting Merit List", sp_name)
            if existing_sp.docstatus == 1:
                existing_sp.cancel()
            existing_sp.db_set("status", "Superseded")
            frappe.db.commit()

        sp_doc = frappe.new_doc("Shortlisting Merit List")
        create_filters = {
            "admission_cycle": doc.admission_cycle,
            "campus": doc.campus,
            "program_level": program_level
        }
        if doc.program:
            create_filters["program"] = doc.program
        sp_doc.update(create_filters)
        
        cache_key = f"merit_generation_{doc.admission_cycle}_{doc.campus}_{program_level}_{doc.program or ''}".replace(" ", "_")
        frappe.cache().set_value(cache_key, {
            "status": "In Progress",
            "percent": 85,
            "description": "Creating Shortlisting Merit List..."
        }, expires_in_sec=300)

        sp_doc.generated_on = merit_list_doc.generated_on
        sp_doc.pull_from_merit_list(merit_list_doc)

        doc.status = "Completed"
        doc.generated_on = merit_list_doc.generated_on
        doc.save()

        # Update cache to completed
        frappe.cache().set_value(cache_key, {
            "status": "Completed",
            "percent": 100,
            "description": "Completed"
        }, expires_in_sec=300)

        frappe.db.commit()

        # Link the created process in the message
        total_shortlisted = sp_doc.total_shortlisted or 0
        total_candidates = sp_doc.total_candidates or 0
        total_rejected = max(0, total_candidates - total_shortlisted)

        frappe.msgprint(
            msg=(
                f"Phase 1 Shortlisting Merit List generated. Results pushed to <b><a href='/app/shortlisting-merit-list/{sp_doc.name}'>{sp_doc.name}</a></b>.<br><br>"
                f"<b>Summary:</b><br>"
                f"• Total Entrance Test Passed Candidates: {total_candidates}<br>"
                f"• Shortlisted: {total_shortlisted}<br>"
                f"• Rejected: {total_rejected}"
            ),
            title="Merit List Generated",
            indicator="green",
            primary_action={
                "label": "View Merit List",
                "client_action": "frappe.set_route",
                "args": ["Form", "Shortlisting Merit List", sp_doc.name]
            }
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Merit Generation Failed")
        doc.status = "Failed"
        doc.save()

        # Update cache to failed
        cache_key = f"merit_generation_{doc.admission_cycle}_{doc.campus}_{program_level}_{doc.program or ''}".replace(" ", "_")
        frappe.cache().set_value(cache_key, {
            "status": "Failed",
            "error": str(e),
            "percent": 0
        }, expires_in_sec=60)

        frappe.db.commit()
        raise e


@frappe.whitelist()
def get_generation_progress(docname):
    """
    Returns the cached progress of the merit generation process.
    """
    doc = frappe.get_doc("Merit Generation", docname)
    cache_key = f"merit_generation_{doc.admission_cycle}_{doc.campus}_{doc.generation_type}_{doc.program or ''}".replace(" ", "_")
    progress = frappe.cache().get_value(cache_key) or {}
    
    db_status = frappe.db.get_value("Merit Generation", docname, "status")
    
    if db_status in ["Completed", "Failed"]:
        progress["status"] = db_status
    elif progress.get("status") in ["Completed", "Failed"]:
        pass
    else:
        progress["status"] = db_status or "In Progress"

    if progress.get("status") == "Completed":
        progress["percent"] = 100
        progress["description"] = "Completed"
    elif progress.get("status") == "Failed":
        progress["percent"] = 100
        progress["description"] = "Failed"
    else:
        if "percent" not in progress:
            progress["percent"] = 0
        desc = progress.get("description")
        if not desc or desc in ["Initializing...", "Completed"]:
            progress["description"] = "Processing applicants..."

    return progress
    
