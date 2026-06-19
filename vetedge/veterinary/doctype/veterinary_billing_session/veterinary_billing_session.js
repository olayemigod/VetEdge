frappe.ui.form.on("Veterinary Billing Session", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		frm.add_custom_button(__("Create / Update Draft Invoice"), () => {
			frappe.call({
				method: "vetedge.services.billing_core.create_or_update_invoice_for_billing_session",
				args: { session_name: frm.doc.name },
				freeze: true,
				freeze_message: __("Updating billing invoice..."),
				callback(r) {
					const result = r.message || {};
					if (result.invoice) {
						frappe.show_alert({ message: __("Invoice {0} updated", [result.invoice]), indicator: "green" });
					} else {
						frappe.show_alert({ message: __("No pending charges to invoice"), indicator: "blue" });
					}
					frm.reload_doc();
				},
			});
		}, __("Billing"));

		frm.add_custom_button(__("Refresh Billing Summary"), () => {
			frappe.call({
				method: "vetedge.services.billing_core.refresh_billing_session_summary",
				args: { session_name: frm.doc.name },
				freeze: true,
				callback() {
					frm.reload_doc();
				},
			});
		}, __("Billing"));

		frappe.call({
			method: "vetedge.services.billing_core.get_billing_session_invoice_state",
			args: { session_name: frm.doc.name },
			callback(r) {
				const state = r.message || {};
				const current = state.current_draft_invoice;
				const latest = state.latest_invoice;

				if (current && current.docstatus === 0) {
					frm.add_custom_button(__("Open Current Draft Invoice"), () => {
						frappe.set_route("Form", "Sales Invoice", current.name);
					}, __("Billing"));
				}

				if (latest) {
					frm.add_custom_button(__("View Latest Invoice"), () => {
						frappe.set_route("Form", "Sales Invoice", latest.name);
					}, __("Billing"));
				}
			},
		});
	},
});
