// Copyright (c) 2025, Nishanth and contributors
// For license information, please see license.txt

frappe.ui.form.on("Student Attendance", {
    student(frm) {
        if (frm.doc.student) {
            // Clear class and course to force re-selection
            frm.set_value('class_name', '');
            frm.set_value('course', '');

            // Fetch the classes the student is enrolled in
            frappe.call({
                method: "slcm.slcm.doctype.student_attendance.student_attendance.get_student_classes",
                args: {
                    student: frm.doc.student
                },
                callback: function (r) {
                    if (r.message && r.message.length > 0) {
                        // Filter Class by these classes
                        frm.set_query("class_name", function () {
                            return {
                                filters: {
                                    name: ["in", r.message]
                                }
                            };
                        });
                    } else {
                        // If no enrollments, show empty or all? Default to empty to prevent error
                        frm.set_query("class_name", function () {
                            return {
                                filters: {
                                    name: ["in", []] // Force empty
                                }
                            };
                        });
                        frappe.msgprint(__("Selected student is not enrolled in any class."));
                    }
                }
            });
        }
    }
});
frappe.listview_settings["Student Attendance"] = {
    onload(listview) {
        // Exclude auto-created placeholder records from the list.
        // source="Auto" records are roster entries created by Attendance Session on insert —
        // they are NOT actual marked attendance and should not appear here.
        listview.filter_area.add([
            ["Student Attendance", "source", "!=", "Auto"]
        ]);

        const style = document.createElement("style");
        style.innerHTML = `
            /* Hide ONLY the heart icon */
            .list-row-like {
                display: none !important;
            }

            /* Hide ONLY the comment icon + count */
            .list-row-activity .comment-count,
            .list-row-activity .comments,
            .list-row-activity .comment-icon,
            .list-row-activity svg.icon-xs {
                display: none !important;
            }
        `;
        document.head.appendChild(style);
    },

    refresh(_listview) {
        $("span.sidebar-toggle-btn").hide();
        $(".col-lg-2.layout-side-section").hide();
    },
};
