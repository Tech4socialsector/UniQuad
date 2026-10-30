frappe.listview_settings['SLCM Payment Request'] = {
    onload: function(listview) {
        listview.page.add_inner_button(__("Bulk Sync Settlements"), function() {
            frappe.confirm(
                __("Are you sure you want to bulk sync settlements for ALL past Payment Requests? This will run in the background and might take several minutes depending on the volume."),
                function() {
                    frappe.call({
                        method: "slcm.api.sync_settlements.enqueue_bulk_sync",
                        callback: function(r) {
                            if(r.message) {
                                frappe.msgprint({
                                    title: __("Sync Queued"),
                                    indicator: "green",
                                    message: __("Bulk Sync has been queued in the background. It will securely pull all historical settlements from Razorpay and update your Payment Requests shortly.")
                                });
                            }
                        }
                    });
                }
            );
        });
    }
};
