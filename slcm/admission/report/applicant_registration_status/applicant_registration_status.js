frappe.query_reports["Applicant Registration Status"] = {
    filters: [
        {
            fieldname: "from_date",
            label: "From Date",
            fieldtype: "Date",
        },
        {
            fieldname: "to_date",
            label: "To Date",
            fieldtype: "Date",
        },
        {
            fieldname: "user",
            label: "User",
            fieldtype: "Link",
            options: "User",
        },
        {
            fieldname: "case",
            label: "Case",
            fieldtype: "Select",
            options: ["All", "With Application", "Without Application", "Enrolled"],
            default: "All",
        },
    ],

    onload: function (report) {
        report.page.add_inner_button("Download Excel", function () {
            let filters = report.get_values() || {};
            
            frappe.show_progress("Exporting Excel", 30, 100, "Generating file...");

            let args = {
                cmd: "frappe.desk.query_report.export_query",
                report_name: report.report_name,
                file_format_type: "Excel",
                filters: JSON.stringify(filters),
                csrf_token: frappe.csrf_token
            };

            let form_data = new FormData();
            for (let key in args) {
                form_data.append(key, args[key]);
            }

            fetch('/api/method/frappe.desk.query_report.export_query', {
                method: 'POST',
                body: form_data,
                headers: {
                    'X-Frappe-CSRF-Token': frappe.csrf_token
                }
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Export failed. Please check the error logs.');
                }
                return response.blob();
            })
            .then(blob => {
                frappe.show_progress("Exporting Excel", 100, 100, "Done");
                setTimeout(() => frappe.hide_progress(), 1000);
                
                let objectUrl = window.URL.createObjectURL(blob);
                let a = document.createElement('a');
                a.href = objectUrl;
                a.download = report.report_name + '.xlsx';
                document.body.appendChild(a);
                a.click();
                a.remove();
                window.URL.revokeObjectURL(objectUrl);
            })
            .catch(error => {
                frappe.hide_progress();
                frappe.msgprint({
                    title: __('Export Failed'),
                    indicator: 'red',
                    message: error.message
                });
            });
        }).addClass("btn-primary");
    },
};
