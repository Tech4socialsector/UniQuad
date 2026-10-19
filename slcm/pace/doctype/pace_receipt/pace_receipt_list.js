frappe.listview_settings['PACE Receipt'] = {
	onload: function (listview) {
		// PACE Receipt specific event names: other list views call off('bulk_download_complete'),
		// which would silently remove a handler on the shared name
		frappe.realtime.off('bulk_pace_receipt_download_progress');
		frappe.realtime.on('bulk_pace_receipt_download_progress', (data) => {
			frappe.show_progress(data.title, data.progress[0], 100, data.description);
		});

		frappe.realtime.off('pace_receipt_bulk_download_complete');
		frappe.realtime.on('pace_receipt_bulk_download_complete', (data) => {
			frappe.hide_progress();
			if (data && data.file_url) {
				download_pace_receipt_file(data.file_url);
				frappe.show_alert({ message: __('Bulk download ready. Download started.'), indicator: 'green' });
			}
		});

		frappe.realtime.off('pace_receipt_bulk_download_failed');
		frappe.realtime.on('pace_receipt_bulk_download_failed', (data) => {
			frappe.hide_progress();
			frappe.msgprint({
				title: __('Bulk Download Failed'),
				indicator: 'red',
				message: (data && data.message) || __('Bulk download failed.'),
			});
		});

		listview.page.add_inner_button(__('Bulk Download'), function () {
			let dialog = new frappe.ui.Dialog({
				title: __('Bulk download PACE payment receipts'),
				fields: [
					{
						label: __('Programme'),
						fieldname: 'program',
						fieldtype: 'Link',
						options: 'PACE Programme',
					},
					{
						label: __('Fee Type'),
						fieldname: 'fee_type',
						fieldtype: 'Select',
						options: '\nApplication Fee\nCourse Fee',
					},
					{
						label: __('From Payment Date'),
						fieldname: 'from_date',
						fieldtype: 'Date',
					},
					{
						label: __('To Payment Date'),
						fieldname: 'to_date',
						fieldtype: 'Date',
					},
					{
						label: __('Output Format'),
						fieldname: 'output_format',
						fieldtype: 'Select',
						options: 'ZIP Archive\nSingle Merged PDF',
						default: 'ZIP Archive',
					},
				],
				primary_action_label: __('Download'),
				primary_action: function (values) {
					dialog.hide();
					
					// Initialize progress bar
					frappe.show_progress(
						__('Preparing PACE receipt bulk download…'),
						0,
						100,
						__('Starting export...')
					);

					frappe.call({
						method: 'slcm.pace.doctype.pace_receipt.pace_receipt.get_bulk_pace_receipts_zip',
						args: { filters: values },
						callback: function (r) {
							if (!r.message) {
								frappe.hide_progress();
								return;
							}
							if (typeof r.message === 'string') {
								frappe.hide_progress();
								download_pace_receipt_file(r.message);
							} else if (r.message.status === 'enqueued' || r.message.status === 'already_running') {
								frappe.msgprint({
									title: __('Background job started'),
									message: r.message.message,
									indicator: 'blue',
								});
							} else {
								frappe.hide_progress();
							}
						},
						error: function() {
							frappe.hide_progress();
						}
					});
				},
			});
			dialog.show();
		});
	},
};

// Downloads via a link click instead of window.open, which popup blockers stop when called after an async call
function download_pace_receipt_file(file_url) {
	const link = document.createElement('a');
	link.href = file_url;
	link.download = '';
	document.body.appendChild(link);
	link.click();
	link.remove();
}
