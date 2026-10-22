# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
import json
import re
import traceback
from frappe.model.document import Document
from frappe.utils import get_url
from frappe.utils.pdf import get_pdf


class EntranceTestList(Document):

    def autoname(self):
        """
        Custom naming series for Entrance Test List records.
        """
        if self.academic_year:
            prefix = f"ETL-{self.academic_year}-"

            rows = frappe.db.sql(
                """SELECT name
                   FROM `tabEntrance Test List`
                   WHERE name LIKE %s""",
                prefix + "%",
                as_list=True,
            )

            used = set()

            pattern = re.compile(re.escape(prefix) + r"(\d{1,})$")
            for r in rows:
                name = r[0]
                m = pattern.match(name)
                if m:
                    try:
                        used.add(int(m.group(1)))
                    except ValueError:
                        pass

            idx = 1
            while idx in used:
                idx += 1

            self.name = f"{prefix}{idx:03d}"
        else:
            self.name = frappe.generate_hash(self.doctype, 6)

    def validate(self):
        """Sync applicant details on save to ensure data integrity, especially for manually added rows."""
        if self.entrance_test_applicant:
            app_ids = [row.applicant_id for row in self.entrance_test_applicant if row.applicant_id]
            if app_ids:
                apps = frappe.get_all("Applicant", 
                    filters={"name": ["in", app_ids]},
                    fields=["name", "candidate_name", "program", "program_level", "email", "gender", "pwd", "entrance_test", "intereview"]
                )
                app_map = {a.name: a for a in apps}
                
                ees = frappe.get_all("Eligibility Evaluation",
                    filters={"applicant_name": ["in", app_ids]},
                    fields=["applicant_name", "exempts_entrance_test", "exempts_interview"]
                )
                ee_map = {e.applicant_name: e for e in ees}

                for row in self.entrance_test_applicant:
                    if row.applicant_id and row.applicant_id in app_map:
                        a = app_map[row.applicant_id]
                        row.candidate_name = a.candidate_name
                        row.program = a.program
                        row.program_level = a.program_level
                        row.email = a.email
                        row.gender = a.gender
                        row.pwd = 1 if str(a.pwd or "").strip().lower() == "yes" else 0
                        row.entrance_test = a.entrance_test
                        row.intereview = a.intereview
                        
                        ee = ee_map.get(row.applicant_id)
                        if ee:
                            row.exempts_entrance_test = ee.exempts_entrance_test
                            row.exempts_interview = ee.exempts_interview

        self.set_allocation_status()

    def set_allocation_status(self):
        if not self.entrance_test_applicant:
            self.allocation_status = "Draft"
            return
            
        allocated_count = sum(1 for row in self.entrance_test_applicant if row.allocation_status in ("Allocated", "Converted"))
        total_count = len(self.entrance_test_applicant)
        
        if allocated_count == 0:
            self.allocation_status = "Draft"
        elif allocated_count == total_count:
            self.allocation_status = "Completed"
        else:
            self.allocation_status = "Partially Completed"

    @frappe.whitelist()
    @frappe.whitelist()
    def allocate_seats(self, providers, selected_applicants, allocation_date=None, entrance_test_name=None, allocation_type=None, send_email=1):
        """
        Logic:
          - If allocation_type == "Allocate Directly":
              - Directly allocates seat to selected entrance test centre.
              - Decrements available capacity & updates reserved seats.
              - Generates Admit Card PDF immediately.
              - Sends email WITH Admit Card attached.
          - If allocation_type == "Allow Applicant Selection":
              - Stores selected centres in assigned_preferences child table.
              - Keeps allocation_status as 'Not Allocated'.
              - Sends email notifying applicant to select preference on portal.
              - Admit card generated later when applicant confirms preference on portal.
        """
        frappe.reload_doc("admission", "doctype", "entrance_test_preference_assigned")
        frappe.reload_doc("admission", "doctype", "entrance_test_seat_allocation")
        frappe.clear_cache(doctype="Entrance Test Seat Allocation")
        
        if isinstance(providers, str):
            providers = json.loads(providers)
        if isinstance(selected_applicants, str):
            selected_applicants = json.loads(selected_applicants)

        if not providers:
            frappe.throw("No providers selected.")
        if not selected_applicants:
            frappe.throw("No applicants selected.")

        if not allocation_type:
            allocation_type = "Allow Applicant Selection"

        provider_list = []
        for pname in providers:
            pdoc = frappe.get_doc("Entrance Test Provider", pname)
            if not pdoc.active:
                frappe.throw(f"Provider '{pname}' is not active.")
            provider_list.append(pdoc)

        applicant_map = {app.name: app for app in self.entrance_test_applicant}

        created_count = 0
        unallocated_list = []
        total_applicants = len(selected_applicants)
        test_cfg_cache = {}

        for i, app_name in enumerate(selected_applicants):
            app = applicant_map.get(app_name)
            if not app:
                continue

            if getattr(app, "allocation_status", "") in ("Allocated", "Converted"):
                continue

            # Publish real-time WebSocket progress to user interface
            progress_pct = round(float(i + 1) / total_applicants * 100, 1)
            frappe.publish_realtime(
                event="entrance_test_seat_allocation_progress",
                message={
                    "progress": progress_pct,
                    "current": i + 1,
                    "total": total_applicants,
                    "allocated_count": created_count,
                    "applicant_name": getattr(app, "candidate_name", "Unknown") or "Unknown"
                },
                user=frappe.session.user
            )

            try:
                cycle_name = self.admission_cycle
                program_name = getattr(app, "program", None)
                program_level_name = self.program_level

                app_doc = None
                app_pwd = 0
                if getattr(app, "pwd", 0) == 1:
                    app_pwd = 1

                if getattr(app, "applicant_id", None):
                    try:
                        app_doc = frappe.get_doc("Applicant", app.applicant_id)
                        if not cycle_name:
                            cycle_name = app_doc.admission_cycle
                        if not program_name:
                            program_name = app_doc.program
                        if not program_level_name:
                            program_level_name = app_doc.program_level
                        if (getattr(app_doc, "pwd", "") or "").strip().lower() == "yes":
                            app_pwd = 1
                    except Exception:
                        pass

                existing_allocation = frappe.db.get_value("Entrance Test Seat Allocation", {
                    "entrance_test_list": self.name,
                    "applicant": app.applicant_id
                }, "name")

                if existing_allocation:
                    allocation = frappe.get_doc("Entrance Test Seat Allocation", existing_allocation)
                else:
                    allocation = frappe.new_doc("Entrance Test Seat Allocation")
                    allocation.entrance_test_list    = self.name
                    allocation.academic_year         = self.academic_year
                    allocation.admission_cycle       = self.admission_cycle
                    allocation.campus                = self.campus
                    allocation.program_level         = self.program_level

                    allocation.applicant             = app.applicant_id
                    allocation.candidate_name        = app.candidate_name
                    allocation.program               = app.program
                    allocation.email                 = app.email
                    allocation.gender                = app.gender
                    allocation.pwd                   = app_pwd
                    allocation.entrance_test         = getattr(app, "entrance_test", 0)
                    allocation.intereview            = getattr(app, "intereview", 0)
                    allocation.exempts_entrance_test = getattr(app, "exempts_entrance_test", 0)
                    allocation.exempts_interview     = getattr(app, "exempts_interview", 0)
                    allocation.allocation_status      = "Not Allocated"
                    allocation.entrance_test_status   = "Scheduled"
                
                allocation.pwd = app_pwd

                cache_key = (cycle_name, program_name, program_level_name)
                if cache_key in test_cfg_cache:
                    test_cfg = test_cfg_cache[cache_key]
                else:
                    test_cfg = _resolve_entrance_test_details_from_cycle(cycle_name, program_name, program_level_name)
                    test_cfg_cache[cache_key] = test_cfg

                resolved_test_name = test_cfg.get("entrance_test_name") or entrance_test_name
                resolved_test_date = test_cfg.get("entrance_test_date") or allocation_date
                resolved_start_time = test_cfg.get("start_time")
                resolved_end_time = test_cfg.get("end_time")

                if resolved_test_name:
                    allocation.entrance_test_name = resolved_test_name

                if resolved_test_date:
                    if resolved_start_time:
                        allocation.allocation_date = f"{resolved_test_date} {resolved_start_time}"
                    else:
                        allocation.allocation_date = str(resolved_test_date)
                elif allocation_date:
                    allocation.allocation_date = allocation_date

                if resolved_start_time:
                    allocation.start_time = resolved_start_time
                if resolved_end_time:
                    allocation.end_time = resolved_end_time

                allocation.set("assigned_preferences", [])
                for idx, pdoc in enumerate(provider_list, start=1):
                    allocation.append("assigned_preferences", {
                        "provider": pdoc.name,
                        "center_name": pdoc.center_name,
                        "center_address": pdoc.center_address,
                        "preference_order": idx
                    })

                # Fetch categories from Applicant
                if allocation.applicant and (not allocation.category or allocation.is_new()):
                    try:
                        if not app_doc:
                            app_doc = frappe.get_doc("Applicant", allocation.applicant)
                        app_categories = app_doc._get_applicant_categories()
                        if not allocation.category:
                            for cat in app_categories:
                                allocation.append("category", {"category": cat})
                    except Exception:
                        pass

                if allocation_type == "Allocate Directly":
                    sel_provider = None
                    failure_reason = None

                    for pdoc in provider_list:
                        # Check PWD facility
                        if app_pwd and not getattr(pdoc, "pwd_accessible", 0):
                            failure_reason = f"Centre '{pdoc.center_name}' does not have facility to accommodate PWD students."
                            continue

                        # Check total capacity
                        avail = pdoc.available_capacity or 0
                        if avail <= 0:
                            failure_reason = f"Centre '{pdoc.center_name}' has no available capacity."
                            continue

                        # Check programme capacity if defined
                        prog_capacity_ok = True
                        if hasattr(pdoc, "programme_capacity") and pdoc.programme_capacity and allocation.program:
                            for r in pdoc.programme_capacity:
                                if r.program == allocation.program:
                                    if (r.available_capacity or 0) <= 0:
                                        prog_capacity_ok = False
                                        failure_reason = f"Centre '{pdoc.center_name}' has no available capacity for programme '{allocation.program}'."
                                    break

                        if not prog_capacity_ok:
                            continue

                        sel_provider = pdoc
                        break

                    if not sel_provider:
                        unallocated_list.append({
                            "name": app.candidate_name or "Unknown",
                            "applicant_id": app.applicant_id or app_name,
                            "reason": failure_reason or "Selected centre is not available or full."
                        })
                        continue

                    if hasattr(sel_provider, "programme_capacity") and sel_provider.programme_capacity and allocation.program:
                        for r in sel_provider.programme_capacity:
                            if r.program == allocation.program:
                                r.reserved_seats = (r.reserved_seats or 0) + 1
                                r.available_capacity = max(0, (r.capacity or 0) - r.reserved_seats)
                                break

                    sel_provider.reserved_seats = (sel_provider.reserved_seats or 0) + 1
                    sel_provider.calculate_capacity()
                    # We will save the provider once at the end of the batch allocation instead of every loop iteration

                    seat_number = f"{(sel_provider.reserved_seats):02d}"
                    allocation.entrance_test_provider = sel_provider.name
                    allocation.center_name            = sel_provider.center_name
                    allocation.center_address         = sel_provider.center_address
                    allocation.seat_number            = seat_number
                    allocation.allocation_status      = "Allocated"
                    allocation.allocated_by           = frappe.session.user

                    # Generate structured admit card number immediately for instant availability
                    admit_card_number = _generate_admit_card_number(allocation, is_rescheduled=False)
                    if admit_card_number:
                        allocation.admit_card_number = admit_card_number

                    # Prevent on_update hook from synchronously generating the admit card
                    allocation.flags.ignore_admit_card_generation = True
                    allocation.save(ignore_permissions=True)

                    # Assign a dynamic URL for lazy PDF generation to maintain fast bulk processing speeds
                    # We use allocation.name here since the document is now safely saved and has an ID
                    dummy_url = f"/api/method/slcm.www.nlsat.eligibility.entrance_test_seat_allocation.download_admit_card?allocation_name={allocation.name}"
                    frappe.db.set_value(allocation.doctype, allocation.name, "admit_card_download", dummy_url)

                else:
                    if app_pwd:
                        has_pwd_center = any(getattr(pdoc, "pwd_accessible", 0) for pdoc in provider_list)
                        if not has_pwd_center:
                            unallocated_list.append({
                                "name": app.candidate_name or "Unknown",
                                "applicant_id": app.applicant_id or app_name,
                                "reason": "None of the selected centres have PWD accessibility facility."
                            })
                            continue

                    allocation.allocation_status = "Not Allocated"
                    allocation.save(ignore_permissions=True)

                email = allocation.email or ""
                if not email and allocation.applicant:
                    try:
                        app_email = frappe.db.get_value("Applicant", allocation.applicant, "email")
                        if app_email:
                            email = app_email
                    except Exception:
                        pass

                if email and frappe.utils.cint(send_email):
                    try:
                        _send_allocation_email(allocation, email, allocation_type)
                        _send_allocation_notification(allocation, email)
                    except Exception:
                        frappe.log_error(
                            message=traceback.format_exc(),
                            title=f"Allocation Email/Notification Failed: {allocation.name}"
                        )

                # Immediately change the status in the database for tracking and persistence
                frappe.db.set_value("Entrance Test Applicant", app.name, "allocation_status", "Allocated")
                app.allocation_status = "Allocated"
                created_count += 1
                
                # Commit instantly for each allocated applicant so no work is lost if interrupted
                frappe.db.commit()

            except Exception as e:
                frappe.db.rollback()
                frappe.log_error(
                    message=traceback.format_exc(),
                    title=f"Seat Allocation Error for Applicant {getattr(app, 'applicant_id', app_name)}"
                )
                unallocated_list.append({
                    "name": getattr(app, "candidate_name", "Unknown") or "Unknown",
                    "applicant_id": getattr(app, "applicant_id", app_name) or app_name,
                    "reason": f"System error during allocation: {str(e)}"
                })

        # Save updated provider capacities once after the entire loop completes
        for pdoc in provider_list:
            pdoc.save(ignore_permissions=True)
            
        allocated_count = frappe.db.count("Entrance Test Applicant", {"parent": self.name, "allocation_status": ["in", ("Allocated", "Converted")]})
        total_len = len(self.entrance_test_applicant) if self.entrance_test_applicant else 0
        if total_len > 0:
            if allocated_count == 0:
                new_status = "Draft"
            elif allocated_count == total_len:
                new_status = "Completed"
            else:
                new_status = "Partially Completed"
            frappe.db.set_value("Entrance Test List", self.name, "allocation_status", new_status)

        frappe.db.set_value("Entrance Test List", self.name, "modified", frappe.utils.now())
        frappe.db.commit()

        return {
            "allocated_count": created_count,
            "unallocated": unallocated_list
        }

    @frappe.whitelist()
    def check_seat_availability(self, providers, selected_applicants, allocation_type=None):
        """
        Checks seat availability across selected centres for the selected applicants.
        Returns a detailed breakdown by programme and centre for confirmation before allocation.
        Also detects PWD applicants and checks if centres have PWD accessibility.
        """
        if isinstance(providers, str):
            providers = json.loads(providers)
        if isinstance(selected_applicants, str):
            selected_applicants = json.loads(selected_applicants)

        if not providers or not selected_applicants:
            return {"can_allocate": False, "error": "No providers or applicants selected."}

        if not allocation_type:
            allocation_type = "Allow Applicant Selection"

        # Build applicant map from child table
        applicant_map = {app.name: app for app in self.entrance_test_applicant}

        # Count applicants by programme and track PWD applicants
        programme_counts = {}
        programme_pwd_counts = {}
        total_selected = 0
        total_pwd = 0
        pwd_applicants = []

        for app_name in selected_applicants:
            app = applicant_map.get(app_name)
            if not app:
                continue
            if getattr(app, "allocation_status", "") == "Allocated":
                continue
            total_selected += 1
            prog = getattr(app, "program", None) or "Unspecified"
            programme_counts[prog] = programme_counts.get(prog, 0) + 1

            # Check PWD status
            app_pwd = 0
            if getattr(app, "pwd", 0) == 1:
                app_pwd = 1
            elif getattr(app, "applicant_id", None):
                try:
                    pwd_val = frappe.db.get_value("Applicant", app.applicant_id, "pwd") or ""
                    if str(pwd_val).strip().lower() == "yes":
                        app_pwd = 1
                except Exception:
                    pass

            if app_pwd:
                total_pwd += 1
                programme_pwd_counts[prog] = programme_pwd_counts.get(prog, 0) + 1
                pwd_applicants.append({
                    "name": app.candidate_name or "Unknown",
                    "applicant_id": app.applicant_id or app_name,
                    "programme": prog
                })

        if total_selected == 0:
            return {"can_allocate": False, "error": "No unallocated applicants found in selection."}

        # Get provider details with capacity
        centre_details = []
        total_available = 0
        has_pwd_centre = False

        for pname in providers:
            try:
                pdoc = frappe.get_doc("Entrance Test Provider", pname)
            except Exception:
                continue

            avail = pdoc.available_capacity or 0
            total_available += avail

            is_pwd_accessible = getattr(pdoc, "pwd_accessible", 0) == 1
            if is_pwd_accessible:
                has_pwd_centre = True

            centre_prog_caps = {}
            if hasattr(pdoc, "programme_capacity") and pdoc.programme_capacity:
                for row in pdoc.programme_capacity:
                    prog_avail = max(0, (row.capacity or 0) - (row.reserved_seats or 0))
                    centre_prog_caps[row.program] = {
                        "capacity": row.capacity or 0,
                        "reserved": row.reserved_seats or 0,
                        "available": prog_avail
                    }

            centre_details.append({
                "provider": pname,
                "center_name": pdoc.center_name or pname,
                "total_capacity": pdoc.total_capacity or 0,
                "reserved_seats": pdoc.reserved_seats or 0,
                "available_capacity": avail,
                "pwd_accessible": 1 if is_pwd_accessible else 0,
                "programme_capacities": centre_prog_caps
            })

        # Build programme-wise breakdown
        programme_breakdown = []
        has_shortage = False
        for prog, count in sorted(programme_counts.items()):
            # Sum available capacity for this programme across all centres
            prog_total_available = 0
            centre_avails = []
            for cd in centre_details:
                prog_caps = cd["programme_capacities"]
                if prog in prog_caps:
                    prog_total_available += prog_caps[prog]["available"]
                    centre_avails.append({
                        "center_name": cd["center_name"],
                        "available": prog_caps[prog]["available"],
                        "capacity": prog_caps[prog]["capacity"],
                        "reserved": prog_caps[prog]["reserved"]
                    })
                else:
                    # If centre has no programme-specific capacity, use overall
                    centre_avails.append({
                        "center_name": cd["center_name"],
                        "available": cd["available_capacity"],
                        "capacity": cd["total_capacity"],
                        "reserved": cd["reserved_seats"]
                    })
                    prog_total_available += cd["available_capacity"]

            shortage = max(0, count - prog_total_available)
            if shortage > 0:
                has_shortage = True

            programme_breakdown.append({
                "programme": prog,
                "applicant_count": count,
                "pwd_count": programme_pwd_counts.get(prog, 0),
                "total_available": prog_total_available,
                "shortage": shortage,
                "sufficient": shortage == 0,
                "centre_details": centre_avails
            })

        # Effective available = sum of programme-level availability for selected programmes
        effective_total_available = sum(p["total_available"] for p in programme_breakdown)

        # PWD conflict detection
        pwd_conflict = total_pwd > 0 and not has_pwd_centre

        return {
            "can_allocate": True,
            "allocation_type": allocation_type,
            "total_selected": total_selected,
            "total_available_seats": total_available,
            "effective_total_available": effective_total_available,
            "overall_sufficient": effective_total_available >= total_selected,
            "has_programme_shortage": has_shortage,
            "programme_breakdown": programme_breakdown,
            "centre_details": centre_details,
            "total_pwd": total_pwd,
            "has_pwd_centre": has_pwd_centre,
            "pwd_conflict": pwd_conflict,
            "pwd_applicants": pwd_applicants
        }

    @frappe.whitelist()
    def get_next_preference_applicants(self):
        applicants = []
        for row in self.entrance_test_applicant:
            if not row.applicant_id:
                continue
            # Skip applicants already fully allocated, converted to another city, or cancelled
            if row.allocation_status in ("Allocated", "Converted", "Cancelled", "Rejected"):
                continue

            app_doc = frappe.get_all("Applicant", filters={"name": row.applicant_id}, fields=["first_preference", "second_preference", "third_preference"], limit=1)
            if not app_doc:
                continue
            app_doc = app_doc[0]
            current_city = self.entrance_test_city
            
            next_city = None
            preference_step = ""
            
            if current_city == app_doc.first_preference and app_doc.second_preference:
                next_city = app_doc.second_preference
                preference_step = "Preference 2"
            elif current_city == app_doc.second_preference and app_doc.third_preference:
                next_city = app_doc.third_preference
                preference_step = "Preference 3"
            
            # If no next city, mark as "Not Exists"
            if not next_city:
                preference_step = "Not Exists"

            applicants.append({
                "name": row.name,
                "applicant_id": row.applicant_id,
                "candidate_name": row.candidate_name,
                "program": row.program,
                "allocation_status": row.allocation_status,
                "previous_preference": current_city,
                "next_preference": next_city or "",
                "preference_step": preference_step,
                "has_next": 1 if next_city else 0
            })
        return applicants

    @frappe.whitelist()
    def generate_next_preference_lists(self, selected_applicants):
        if isinstance(selected_applicants, str):
            selected_applicants = json.loads(selected_applicants)
        
        # Group selected applicants by next_preference city
        city_applicants = {}
        for row_name in selected_applicants:
            row = frappe.get_doc("Entrance Test Applicant", row_name)
            app_doc = frappe.get_all("Applicant", filters={"name": row.applicant_id}, fields=["first_preference", "second_preference", "third_preference"], limit=1)
            if not app_doc:
                continue
            app_doc = app_doc[0]
            current_city = self.entrance_test_city
            
            next_city = None
            if current_city == app_doc.first_preference and app_doc.second_preference:
                next_city = app_doc.second_preference
            elif current_city == app_doc.second_preference and app_doc.third_preference:
                next_city = app_doc.third_preference
                
            if next_city:
                if next_city not in city_applicants:
                    city_applicants[next_city] = []
                city_applicants[next_city].append(row)
        
        from frappe.utils import now
        created_lists = []
        for city, rows in city_applicants.items():
            existing = frappe.get_all("Entrance Test List", filters={
                "academic_year": self.academic_year,
                "admission_cycle": self.admission_cycle,
                "program_level": self.program_level,
                "program": self.program,
                "entrance_test_city": city
            }, limit=1)
            
            if existing:
                new_list = frappe.get_doc("Entrance Test List", existing[0].name)
            else:
                new_list = frappe.new_doc("Entrance Test List")
                new_list.academic_year = self.academic_year
                new_list.admission_cycle = self.admission_cycle
                new_list.program_level = self.program_level
                new_list.program = self.program
                new_list.entrance_test_city = city
                new_list.campus = self.campus
                new_list.status = "Generated"
                new_list.generated_on = now()
                new_list.save()
            
            # Add rows to the new list
            for row in rows:
                exists = False
                for existing_row in new_list.entrance_test_applicant:
                    if existing_row.applicant_id == row.applicant_id:
                        exists = True
                        break
                if not exists:
                    new_list.append("entrance_test_applicant", {
                        "applicant_id": row.applicant_id,
                        "candidate_name": row.candidate_name,
                        "program": row.program,
                        "program_level": row.program_level,
                        "email": row.email,
                        "gender": row.gender,
                        "pwd": row.pwd,
                        "entrance_test": row.entrance_test,
                        "intereview": row.intereview,
                        "exempts_entrance_test": row.exempts_entrance_test,
                        "exempts_interview": row.exempts_interview,
                        "allocation_status": "Not Allocated"
                    })
            new_list.save()
            created_lists.append(new_list.name)
            
            # Update original rows to Converted
            for row in rows:
                frappe.db.set_value("Entrance Test Applicant", row.name, "allocation_status", "Converted")
                row.allocation_status = "Converted"
            frappe.db.commit()
            
        # Update allocation status for current list
        allocated_count = frappe.db.count("Entrance Test Applicant", {"parent": self.name, "allocation_status": ["in", ("Allocated", "Converted")]})
        total_len = len(self.entrance_test_applicant) if self.entrance_test_applicant else 0
        if total_len > 0:
            if allocated_count == 0:
                new_status = "Draft"
            elif allocated_count == total_len:
                new_status = "Completed"
            else:
                new_status = "Partially Completed"
            frappe.db.set_value("Entrance Test List", self.name, "allocation_status", new_status)
            frappe.db.commit()
        
        return created_lists


def _send_allocation_email(allocation, email, allocation_type=None):
    """Send a formal Entrance Test Centre Selection / Allocation email to the applicant."""
    try:
        if allocation_type == "Allocate Directly":
            template_name = "Automated Entrance Test Allocation"
            attach_admit_card = False
        else:
            template_name = "Entrance Test Allocation"
            attach_admit_card = False

        if not frappe.db.exists("Email Template", template_name):
            frappe.log_error(f"Email Template '{template_name}' not found.", "Email Sending Error")
            return

        template = frappe.get_doc("Email Template", template_name)
        
        doc_dict = allocation.as_dict()
        doc_dict["assigned_preferences"] = [p.as_dict() for p in allocation.assigned_preferences]
        if getattr(allocation, "is_reallocation", False):
            doc_dict["is_reallocation"] = True
            doc_dict["old_center_name"] = getattr(allocation, "old_center_name", "")
        
        args = {
            "doc": doc_dict,
            "portal_url": get_url("/nlsat/dashboard?panel=applications")
        }

        subject = frappe.render_template(template.subject, args)
        
        # Determine the content field correctly
        message_body = ""
        if template.get("use_html"):
            message_body = frappe.render_template(template.response_html, args)
        else:
            message_body = frappe.render_template(template.response, args)

        if not message_body:
            message_body = frappe.render_template(template.get("message") or "", args)
            
        # Robust CC handling from the manual 'cc' field added to Email Template
        cc_list = []
        cc_field_value = template.get("cc")
        if cc_field_value:
            cc_list = [c.strip() for c in cc_field_value.replace(";", ",").split(",") if c.strip()]
        
        if message_body:
            attachments = []
            if attach_admit_card and allocation.allocation_status == "Allocated" and getattr(allocation, "admit_card_download", None):
                attachments.append({
                    "file_url": allocation.admit_card_download
                })

            try:
                # Use now=False to queue the email.
                sender = None
                if template.get("email_account"):
                    sender = frappe.db.get_value("Email Account", template.get("email_account"), "email_id") or template.get("email_account")

                frappe.sendmail(
                    recipients=[email],
                    sender=sender,
                    cc=cc_list,
                    subject=subject,
                    message=message_body,
                    attachments=attachments,
                    reference_doctype="Entrance Test Seat Allocation",
                    reference_name=allocation.name,
                    now=False
                )
                frappe.logger().info(f"Entrance Test Allocation Email queued successfully to {email} for {allocation.name}")
            except Exception:
                frappe.log_error(traceback.format_exc(), f"Entrance Test Allocation Email Queueing Failed: {allocation.name}")
    except Exception:
        frappe.log_error(message=traceback.format_exc(), title=f"Allocation Email Failed: {allocation.name}")


@frappe.whitelist()
def get_applicant_preferences(applicant_id, entrance_test_list):
    allocation_name = frappe.db.get_value("Entrance Test Seat Allocation", {
        "applicant": applicant_id,
        "entrance_test_list": entrance_test_list
    }, "name")

    if not allocation_name:
        return []

    try:
        allocation = frappe.get_doc("Entrance Test Seat Allocation", allocation_name, ignore_permissions=True)
    except frappe.DoesNotExistError:
        return []
    
    use_rescheduled = getattr(allocation, "is_rescheduled", 0) == 1 and \
                      getattr(allocation, "re_allocation_status", "") in ["Preferences Assigned", "Allocated", "Reallocated"]
    
    pref_field = "re_assigned_preferences" if use_rescheduled else "assigned_preferences"
    status_field = "re_allocation_status" if use_rescheduled else "allocation_status"
    seat_field = "re_seat_number" if use_rescheduled else "seat_number"
    room_field = "re_room_name" if use_rescheduled else "room_name"

    preferences = []
    for p in allocation.get(pref_field):
        preferences.append({
            "entrance_test_provider": p.provider,
            "center_name": p.center_name,
            "center_address": p.center_address,
            "preference_order": p.preference_order,
            "is_full": _get_remaining_capacity(p.provider, allocation.program) <= 0,
            "allocation_status": getattr(allocation, status_field),
            "seat_number": getattr(allocation, seat_field),
            "room_name": getattr(allocation, room_field)
        })

    return preferences


@frappe.whitelist()
def confirm_applicant_preference(allocation_name, selected_provider):
    allocation = frappe.get_doc("Entrance Test Seat Allocation", allocation_name)

    if allocation.allocation_status == "Allocated":
        frappe.throw("You have already been allocated a seat.")

    provider = frappe.get_doc("Entrance Test Provider", selected_provider)

    avail = (provider.available_capacity or 0)
    if avail <= 0:
        frappe.throw(
            f"Sorry, '{provider.center_name}' is now full. "
            "Please choose another preference center."
        )

    # Check and update specific Programme Capacity row if present
    if hasattr(provider, "programme_capacity") and provider.programme_capacity and allocation.program:
        for r in provider.programme_capacity:
            if r.program == allocation.program:
                r_avail = r.available_capacity if r.available_capacity is not None else max(0, (r.capacity or 0) - (r.reserved_seats or 0))
                if r_avail <= 0:
                    frappe.throw(
                        f"Sorry, '{provider.center_name}' has no available capacity for programme '{allocation.program}'."
                    )
                r.reserved_seats = (r.reserved_seats or 0) + 1
                r.available_capacity = max(0, (r.capacity or 0) - r.reserved_seats)
                break

    new_reserved = (provider.reserved_seats or 0) + 1
    seat_number  = f"{new_reserved:02d}"

    allocation.entrance_test_provider = selected_provider
    allocation.center_name            = provider.center_name
    allocation.center_address         = provider.center_address
    allocation.seat_number            = seat_number
    allocation.allocation_status      = "Allocated"
    allocation.allocated_by           = frappe.session.user
    allocation.save(ignore_permissions=True)

    provider.calculate_capacity()
    provider.save(ignore_permissions=True)

    frappe.db.commit()

    generate_and_store_admit_card(allocation, is_rescheduled=False)

    return {
        "seat_number":    seat_number,
        "room_name":      "",
        "center_name":    provider.center_name,
        "center_address": provider.center_address,
    }


@frappe.whitelist()
def confirm_rescheduled_preference(allocation_name, selected_provider):
    allocation = frappe.get_doc("Entrance Test Seat Allocation", allocation_name)

    if allocation.re_allocation_status == "Allocated":
        frappe.throw("You have already been allocated a seat for the rescheduled test.")

    provider = frappe.get_doc("Entrance Test Provider", selected_provider)

    avail = (provider.available_capacity or 0)
    if avail <= 0:
        frappe.throw(
            f"Sorry, '{provider.center_name}' is now full. "
            "Please choose another preference center."
        )

    # Check and update specific Programme Capacity row if present
    if hasattr(provider, "programme_capacity") and provider.programme_capacity and allocation.program:
        for r in provider.programme_capacity:
            if r.program == allocation.program:
                r_avail = r.available_capacity if r.available_capacity is not None else max(0, (r.capacity or 0) - (r.reserved_seats or 0))
                if r_avail <= 0:
                    frappe.throw(
                        f"Sorry, '{provider.center_name}' has no available capacity for programme '{allocation.program}'."
                    )
                r.reserved_seats = (r.reserved_seats or 0) + 1
                r.available_capacity = max(0, (r.capacity or 0) - r.reserved_seats)
                break

    new_reserved = (provider.reserved_seats or 0) + 1
    seat_number  = f"{new_reserved:02d}"

    allocation.re_entrance_test_provider = selected_provider
    allocation.re_center_name            = provider.center_name
    allocation.re_center_address         = provider.center_address
    allocation.re_seat_number            = seat_number
    allocation.re_allocation_status      = "Allocated"
    allocation.re_allocated_by           = frappe.session.user
    allocation.save(ignore_permissions=True)

    provider.calculate_capacity()
    provider.save(ignore_permissions=True)

    frappe.db.commit()

    generate_and_store_admit_card(allocation, is_rescheduled=True)

    return {
        "seat_number":    seat_number,
        "room_name":      "",
        "center_name":    provider.center_name,
        "center_address": provider.center_address,
    }


def _get_remaining_capacity(provider_name, program=None):
    """Total remaining seats for a provider, or specific programme if specified."""
    try:
        provider = frappe.get_doc("Entrance Test Provider", provider_name)
        if program and provider.get("programme_capacity"):
            for r in provider.programme_capacity:
                if r.program == program:
                    return r.available_capacity if r.available_capacity is not None else max(0, (r.capacity or 0) - (r.reserved_seats or 0))
        return max(0, (provider.available_capacity or 0))
    except Exception:
        return 0


def _generate_admit_card_number(allocation, is_rescheduled=False):
    """
    Generate a structured Admit Card Number in the format:
    [Programme Code][City Code][Centre Code][Student Sequence Number]
    Example: 165070...0016
    - Programme Code: from Programme doctype (program_code field)
    - City Code: from Entrance Test City doctype (city_code field), linked via Provider's city
    - Centre Code: from Entrance Test Provider doctype (provider_code field)
    - Student Sequence: 4-digit zero-padded number starting from 0001, scoped per centre
    """
    provider_name = allocation.re_entrance_test_provider if is_rescheduled else allocation.entrance_test_provider
    program_name = allocation.program

    # 1. Programme Code
    programme_code = ""
    if program_name:
        programme_code = frappe.db.get_value("Programme", program_name, "program_code") or ""

    # 2. City Code & Centre Code from Provider
    city_code = ""
    centre_code = ""
    if provider_name:
        provider_data = frappe.db.get_value(
            "Entrance Test Provider", provider_name,
            ["provider_code", "city"], as_dict=True
        )
        if provider_data:
            centre_code = provider_data.provider_code or ""
            if provider_data.city:
                city_code_val = frappe.db.get_value("Entrance Test City", provider_data.city, "city_code")
                city_code = str(city_code_val) if city_code_val else ""

    # 3. Student Sequence Number (scoped per centre)
    existing_count = frappe.db.count(
        "Entrance Test Seat Allocation",
        filters={
            "entrance_test_provider": provider_name,
            "admit_card_number": ["is", "set"],
            "name": ["!=", allocation.name]
        }
    )
    sequence_number = f"{(existing_count + 1):04d}"

    admit_card_number = f"{programme_code}{city_code}{centre_code}{sequence_number}"
    return admit_card_number


def generate_and_store_admit_card(allocation, is_rescheduled=False, html_content=None):
    if isinstance(allocation, str):
        allocation = frappe.get_doc("Entrance Test Seat Allocation", allocation)

    if getattr(allocation, "is_international_applicant", 0):
        return None

    # Ensure print permissions are bypassed (called from portal under applicant session)
    frappe.flags.ignore_print_permissions = True

    # Generate the structured admit card number first so it's available in the print format
    admit_card_number = _generate_admit_card_number(allocation, is_rescheduled)
    frappe.db.set_value(allocation.doctype, allocation.name, "admit_card_number", admit_card_number)
    allocation.admit_card_number = admit_card_number
    pdf_content = None
    try:
        if html_content:
            html_content = re.sub(r'<script\b[^>]*>([\s\S]*?)<\/script>', '', html_content)
            html = html_content
        else:
            from slcm.www.nlsat.eligibility.entrance_test_seat_allocation import get_admit_card_html
            html = get_admit_card_html(allocation, is_rescheduled)
            
        pdf_content = get_pdf(html, options={"load-error-handling": "ignore"})
    except Exception as e:
        frappe.log_error(
            message=traceback.format_exc(),
            title=f"Admit Card Generation Error for {allocation.name}"
        )
        return None
    
    random_hash = frappe.generate_hash(length=4)
    field_to_update = "re_admit_card_download" if is_rescheduled else "admit_card_download"
    file_name = f"Admit_Card_{allocation.applicant}_{random_hash}.pdf"
    if is_rescheduled:
        file_name = f"Admit_Card_{allocation.applicant}_Rescheduled_{random_hash}.pdf"

    old_file_url = getattr(allocation, field_to_update)
    if old_file_url:
        try:
            old_file_name = frappe.db.get_value("File", {
                "file_url": old_file_url,
                "attached_to_doctype": allocation.doctype,
                "attached_to_name": allocation.name,
                "attached_to_field": field_to_update
            }, "name")
            if old_file_name:
                frappe.delete_doc("File", old_file_name, ignore_permissions=True)
        except Exception:
            pass

    _file = frappe.get_doc({
        "doctype": "File",
        "file_name": file_name,
        "attached_to_doctype": allocation.doctype,
        "attached_to_name": allocation.name,
        "attached_to_field": field_to_update,
        "content": pdf_content,
        "is_private": 1
    })
    _file.save(ignore_permissions=True)    
    values = {
        field_to_update: _file.file_url,
        "admit_card_generated": 1,
        "admit_card_number": admit_card_number
    }
        
    frappe.db.set_value(allocation.doctype, allocation.name, values)
    if not isinstance(allocation, str):
        allocation.update(values)
    frappe.db.commit()
    
    return _file.file_url


def _send_allocation_notification(allocation, email):
    """Creates a Notification Log entry for the applicant."""
    if not email:
        return
    
    # The applicant's email is used as their User ID in the portal
    if frappe.db.exists("User", email):
        try:
            # Custom Title and Message similar to Merit List
            if allocation.is_international_applicant:
                message_body = f"""
                    <p>Your online entrance test has been scheduled.</p>
                    <p>Please check your admission dashboard to view the details.</p>
                    <p><a href="/nlsat/dashboard?panel=applications" style="color: #16a34a; font-weight: bold;">Click here to view details.</a></p>
                """
            else:
                message_body = f"""
                    <p>An entrance test seat has been allocated for you in <strong>"{allocation.entrance_test_list}"</strong>.</p>
                    <p>Please check your admission dashboard to view the details and select your preferred center.</p>
                    <p><a href="/nlsat/dashboard?panel=applications" style="color: #16a34a; font-weight: bold;">Click here to view details.</a></p>
                """
            
            frappe.get_doc({
                "doctype": "Notification Log",
                "subject": "Entrance Test Seat Allocated",
                "for_user": email,
                "type": "Alert",
                "email_content": message_body,
                "document_type": "Entrance Test Seat Allocation",
                "document_name": allocation.name,
                "from_user": frappe.session.user,
                "link": "/nlsat/dashboard?panel=applications"
            }).insert(ignore_permissions=True)
        except Exception:
            # Silently fail for individual notification logs if one user has issues, but log it
            frappe.log_error(message=frappe.get_traceback(), title=f"Allocation Notification Failed: {allocation.name}")


def _resolve_entrance_test_details_from_cycle(cycle_name, program=None, program_level=None):
    """
    Dynamically fetch Entrance Test Details from Admission Cycle based on:
    1) exact programme match
    2) programme_level match
    3) fallback to first row in child table
    """
    if not cycle_name:
        return {}

    rows = frappe.get_all(
        "Entrance Test Details",
        filters={"parent": cycle_name, "parenttype": "Admission Cycle"},
        fields=["programme", "programme_level", "entrance_test_name", "entrance_test_date", "start_time", "end_time", "idx"],
        order_by="idx asc",
    )
    if not rows:
        return {}

    if program:
        for row in rows:
            if (row.get("programme") or "").strip() == (program or "").strip() and row.get("entrance_test_name"):
                return row

    if program_level:
        for row in rows:
            if (row.get("programme_level") or "").strip() == (program_level or "").strip() and row.get("entrance_test_name"):
                return row

    for row in rows:
        if row.get("entrance_test_name"):
            return row

    return {}


@frappe.whitelist()
def get_providers_with_capacity(city=None, campus=None, programme=None):
    filters = {"active": 1}
    if city:
        filters["city"] = city
    elif campus:
        filters["campus"] = campus
        
    providers = frappe.get_all("Entrance Test Provider", 
        filters=filters,
        fields=["name", "center_name", "center_address", "provider_type", "city", "pwd_accessible", "available_capacity", "total_capacity"],
        limit_page_length=100
    )
    
    for p in providers:
        if programme:
            prog_cap = frappe.db.get_value("Programme Capacity", 
                {"parent": p.name, "parenttype": "Entrance Test Provider", "program": programme},
                ["capacity", "reserved_seats", "available_capacity"], as_dict=True)
            if prog_cap:
                avail = prog_cap.available_capacity if prog_cap.available_capacity is not None else max(0, (prog_cap.capacity or 0) - (prog_cap.reserved_seats or 0))
                p.available_capacity = avail
            else:
                p.available_capacity = 0
        else:
            p.available_capacity = p.available_capacity or 0
            
    return providers


@frappe.whitelist()
def start_background_seat_allocation(entrance_test_list, providers, selected_applicants, allocation_date=None, entrance_test_name=None, allocation_type=None):
    """
    Enqueues the seat allocation process to the background queue (Redis Queue).
    Returns immediately to the client with a job confirmation.
    Publishes real-time progress via frappe.publish_realtime to the frontend.
    """
    if isinstance(providers, str):
        providers = json.loads(providers)
    if isinstance(selected_applicants, str):
        selected_applicants = json.loads(selected_applicants)

    user = frappe.session.user

    frappe.enqueue(
        "slcm.admission.doctype.entrance_test_list.entrance_test_list._process_seat_allocation_job",
        queue="long" if len(selected_applicants) > 300 else "default",
        timeout=18000,
        entrance_test_list=entrance_test_list,
        providers=providers,
        selected_applicants=selected_applicants,
        allocation_date=allocation_date,
        entrance_test_name=entrance_test_name,
        allocation_type=allocation_type,
        user=user,
        enqueue_after_commit=True
    )

    return {
        "status": "queued",
        "total_applicants": len(selected_applicants),
        "message": _("Seat allocation process started in the background.")
    }


def _process_seat_allocation_job(entrance_test_list, providers, selected_applicants, allocation_date=None, entrance_test_name=None, allocation_type=None, user=None):
    """
    Background worker job for processing seat allocation safely without timeouts.
    Emits real-time progress via frappe.publish_realtime to the user's browser.
    """
    try:
        etl_doc = frappe.get_doc("Entrance Test List", entrance_test_list)
        result = etl_doc.allocate_seats(
            providers=providers,
            selected_applicants=selected_applicants,
            allocation_date=allocation_date,
            entrance_test_name=entrance_test_name,
            allocation_type=allocation_type
        )
        frappe.publish_realtime(
            event="entrance_test_seat_allocation_completed",
            message={
                "status": "success",
                "allocated_count": result.get("allocated_count", 0),
                "unallocated": result.get("unallocated", []),
                "entrance_test_list": entrance_test_list
            },
            user=user
        )
    except Exception as e:
        frappe.log_error(message=traceback.format_exc(), title=f"Background Seat Allocation Error for {entrance_test_list}")
        frappe.publish_realtime(
            event="entrance_test_seat_allocation_completed",
            message={
                "status": "error",
                "error": str(e),
                "entrance_test_list": entrance_test_list
            },
            user=user
        )

