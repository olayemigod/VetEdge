frappe.ui.form.on("Pet Boarding Care Record", {
	async stay(frm) {
		if (!frm.doc.stay) {
			return;
		}

		const response = await frappe.db.get_value(
			"Pet Boarding Stay",
			frm.doc.stay,
			["booking", "patient", "primary_owner", "service_branch", "kennel"]
		);
		const stay = response?.message || {};
		await frm.set_value({
			booking: stay.booking || null,
			patient: stay.patient || null,
			primary_owner: stay.primary_owner || null,
			service_branch: stay.service_branch || null,
			kennel: stay.kennel || null,
		});
	},
});
