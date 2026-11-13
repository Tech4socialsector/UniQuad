frappe.query_reports["Payments to Refund"] = {
	filters: [
		{ fieldname: "payment_gateway", label: __("Payment Gateway"), fieldtype: "Select", options: "\nRazorpay\nEasebuzz" },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
		{ fieldname: "include_refunded", label: __("Include fully refunded"), fieldtype: "Check" },
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "to_refund" && data && flt(data.to_refund) > 0) {
			value = `<span style="color: var(--orange-600, #c2410c); font-weight: 600;">${value}</span>`;
		}
		return value;
	},
};
