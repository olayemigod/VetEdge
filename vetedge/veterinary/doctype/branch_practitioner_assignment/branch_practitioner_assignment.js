frappe.ui.form.on("Branch Practitioner Assignment", {
	setup(frm) {
		frm.set_query("practitioner", () => ({
			query: "vetedge.services.permissions.get_veterinary_doctor_users",
		}));
	},
});
