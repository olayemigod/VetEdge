frappe.ui.form.on("Branch User Assignment", {
	setup(frm) {
		frm.set_query("user", () => ({
			query: "vetedge.services.permissions.get_system_users",
		}));
	},
});
