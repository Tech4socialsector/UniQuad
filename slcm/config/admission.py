from frappe import _

def get_data():
    return [
        {
            "label": _("Admission"),
            "icon": "octicon octicon-person-add",
            "items": [
                {
                    "type": "doctype",
                    "name": "Applicant",
                    "label": _("Applicants"),
                },
                {
                    "type": "doctype",
                    "name": "Admission Cycle",
                    "label": _("Admission Cycles"),
                },
                {
                    "type": "doctype",
                    "name": "Admission Year",
                    "label": _("Admission Years"),
                }
            ]
        }
    ]
