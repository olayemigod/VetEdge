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
		set_coreedge_platform_visibility(frm);
	},

	enable_registration_billing(frm) {
		set_registration_billing_read_only(frm);
	},

	enable_consultation_billing(frm) {
		set_consultation_billing_read_only(frm);
	},
});

function set_coreedge_platform_visibility(frm) {
	const is_available = frappe.boot && frappe.boot.is_coreedge_available;
	frm.toggle_display("coreedge_platform_section", !!is_available);
	frm.toggle_display("deployment_mode", !!is_available);
	frm.toggle_display("enable_coreedge_platform", !!is_available);
	frm.toggle_display("coreedge_product_app", !!is_available);
	frm.toggle_display("fail_closed_when_coreedge_missing", !!is_available);

	if (is_available) {
		const is_platform_admin = frappe.user.has_role("System Manager") || frappe.user.has_role("CoreEdge Platform Admin");
		const read_only = !is_platform_admin;
		frm.set_df_property("deployment_mode", "read_only", read_only);
		frm.set_df_property("enable_coreedge_platform", "read_only", read_only);
		frm.set_df_property("coreedge_product_app", "read_only", read_only);
		frm.set_df_property("fail_closed_when_coreedge_missing", "read_only", read_only);
	}
}

function set_registration_billing_read_only(frm) {
	const read_only = !frm.doc.enable_registration_billing;
	frm.set_df_property("default_registration_item", "read_only", read_only);
	frm.set_df_property("default_registration_fee", "read_only", read_only);
	frm.set_df_property("auto_create_invoice_on_registration", "read_only", read_only);
	frm.set_df_property("require_payment_before_first_consultation", "read_only", read_only);
	frm.set_df_property("branch_registration_rules", "read_only", read_only);

	const rules_grid = frm.fields_dict.branch_registration_rules?.grid;
	if (rules_grid) {
		rules_grid.cannot_add_rows = read_only;
		rules_grid.cannot_delete_rows = read_only;
		rules_grid.refresh();
	}
}

function set_consultation_billing_read_only(frm) {
	const read_only = !frm.doc.enable_consultation_billing;
	frm.set_df_property("consultation_item", "read_only", read_only);
}
