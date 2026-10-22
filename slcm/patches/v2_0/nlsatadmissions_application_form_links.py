import frappe


def execute():
	"""Point stored Programme apply links at the renamed applicant web form route.

	The portal moved from /admission to /nlsatadmissions (Indian Nationals) and
	/nlsat-international; the applicant web form is now nlsatadmissions/application-form.
	Old links still work through the /admission website_redirects, this just avoids the hop.
	"""
	for field in ("application_form_link", "international_application_form_link"):
		if not frappe.db.has_column("Programme", field):
			continue
		frappe.db.sql(
			f"""
			UPDATE `tabProgramme`
			SET `{field}` = REPLACE(`{field}`, '/admission/application-form', '/nlsatadmissions/application-form')
			WHERE `{field}` LIKE '%/admission/application-form%'
			"""
		)
