frappe.ui.form.on("Admission Round", {
    refresh: function(frm) {
        if (frm.doc.status === "Active" && frm.doc.application_end) {
            const end = new Date(frm.doc.application_end);
            const now = new Date();
            const diff = end - now;
            if (diff > 0) {
                const days = Math.floor(diff / (1000 * 60 * 60 * 24));
                const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
                frm.dashboard.set_headline(
                    `<span style="color: orange; font-weight: bold;">
                    ⏱ Deadline in: ${days} days ${hours} hours
                    </span>`
                );
            }
        }
    }
});