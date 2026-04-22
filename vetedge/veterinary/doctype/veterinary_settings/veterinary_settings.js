frappe.ui.form.on("Veterinary Settings", {
	setup(frm) {
		const item_query = () => ({
			filters: {
				disabled: 0,
				is_sales_item: 1,
				is_stock_item: 0,
			},
		});

		frm.set_query("default_registration_item", item_query);
		frm.set_query("consultation_item", item_query);
		const rules_grid = frm.fields_dict.branch_registration_rules?.grid;
		if (rules_grid) {
			rules_grid.get_field("registration_item").get_query = item_query;
		}
	},

	refresh(frm) {
		set_registration_billing_read_only(frm);
		set_consultation_billing_read_only(frm);
	},

	enable_registration_billing(frm) {
		set_registration_billing_read_only(frm);
	},

	enable_consultation_billing(frm) {
		set_consultation_billing_read_only(frm);
	},
});

function set_registration_billing_read_only(frm) {
	const read_only = !frm.doc.enable_registration_billing;
	frm.set_df_property("default_registration_item", "read_only", read_only);
	frm.set_df_property("default_registration_fee", "read_only", read_only);
}

function set_consultation_billing_read_only(frm) {
	const read_only = !frm.doc.enable_consultation_billing;
	frm.set_df_property("consultation_item", "read_only", read_only);
}
