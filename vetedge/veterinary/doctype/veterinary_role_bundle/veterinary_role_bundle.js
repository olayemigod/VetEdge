# -*- coding: utf-8 -*-
frappe.ui.form.on("Veterinary Role Bundle", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		frm.add_custom_button(__("Apply to User"), () => {
			frappe.prompt(
				[
					{
						fieldname: "target_user",
						fieldtype: "Link",
						label: "Target User",
						options: "User",
						reqd: 1,
					},
				],
				(values) => {
					frappe.call({
						method: "vetedge.services.role_bundles.apply_role_bundle_to_user",
						args: {
							bundle_name: frm.doc.name,
							target_user: values.target_user,
						},
						callback(result) {
							const data = result.message || {};
							frappe.msgprint({
								title: __("Role Bundle Applied"),
								message: __("Added roles: {0}", [(data.added_roles || []).join(", ") || __("None")]),
								indicator: "green",
							});
						},
					});
				},
				__("Apply Role Bundle"),
				__("Apply")
			);
		});
	},
});
