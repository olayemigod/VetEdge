frappe.ui.form.on("Kennel Availability", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}
		frm.add_custom_button(__("Refresh Snapshot"), () => {
			frappe.call({
				method: "vetedge.services.boarding.refresh_kennel_availability",
				args: { snapshot_date: frm.doc.snapshot_date, service_branch: frm.doc.service_branch },
				freeze: true,
				freeze_message: __("Refreshing kennel availability..."),
				callback() {
					frm.reload_doc();
				},
			});
		});
	},
});
