frappe.ui.form.on("Veterinary Hospitalisation", {
	refresh(frm) {
		set_discharge_fields_visibility(frm);
		set_location_help(frm);
		set_activity_help(frm);
		add_hospitalisation_action_buttons(frm);
		add_charge_sheet_action_buttons(frm);
	},
	status(frm) {
		set_discharge_fields_visibility(frm);
	},
});

function set_discharge_fields_visibility(frm) {
	const show_discharge_fields = ["Ready for Discharge", "Discharged"].includes(frm.doc.status);
	frm.toggle_display(["discharged_by", "discharge_datetime", "discharge_summary"], show_discharge_fields);
}

function set_location_help(frm) {
	frm.set_df_property(
		"care_location_type",
		"description",
		"Optional. Use Not Assigned when the patient is admitted for care without a kennel, cage, ward, or other location assignment."
	);
	frm.set_df_property(
		"care_location",
		"description",
		"Optional. Link a Kennel only when hospital care is tied to an existing kennel record."
	);
}

function set_activity_help(frm) {
	frm.set_df_property(
		"activities",
		"description",
		"Record hospitalisation activities here. Billing and stock sync will be handled through a later charge sheet/invoice flow."
	);
}

frappe.ui.form.on("Veterinary Hospitalisation Activity", {
	billable(frm, cdt, cdn) {
		set_activity_row_status_defaults(cdt, cdn);
	},
	stock_affecting(frm, cdt, cdn) {
		set_activity_row_status_defaults(cdt, cdn);
	},
});

function set_activity_row_status_defaults(cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "billing_status", row.billable ? "Pending Charge" : "Not Billable");
	frappe.model.set_value(cdt, cdn, "stock_status", row.stock_affecting ? "Pending" : "Not Applicable");
}

function add_charge_sheet_action_buttons(frm) {
	if (frm.is_new()) {
		return;
	}

	frm.add_custom_button(__("View Charge Summary"), () => {
		frappe.call({
			method: "vetedge.services.hospitalisation.get_hospitalisation_charge_summary",
			args: { hospitalisation_name: frm.doc.name },
			callback(result) {
				const summary = result.message || {};
				frappe.msgprint({
					title: __("Charge Summary"),
					message: [
						`${__("Pending")}: ${format_currency(summary.total_pending || 0)}`,
						`${__("Invoiced")}: ${format_currency(summary.total_invoiced || 0)}`,
						`${__("Cancelled")}: ${format_currency(summary.total_cancelled || 0)}`,
						`${__("Linked Invoice")}: ${summary.linked_invoice || "-"}`,
					].join("<br>"),
				});
			},
		});
	}, __("Billing"));

	if (["Cancelled", "Discharged"].includes(frm.doc.status)) {
		return;
	}

	frm.add_custom_button(__("Build Charge Sheet"), () => {
		frappe.call({
			method: "vetedge.services.hospitalisation.build_hospitalisation_charge_items",
			args: { hospitalisation_name: frm.doc.name },
			freeze: true,
			callback(result) {
				const summary = result.message || {};
				frappe.show_alert({
					message: __(`Created ${summary.created || 0} charge item(s).`),
					indicator: "green",
				});
				frm.reload_doc();
			},
		});
	}, __("Billing"));

	frm.add_custom_button(__("Sync Charges to Invoice"), () => {
		frappe.call({
			method: "vetedge.services.hospitalisation.sync_hospitalisation_charges_to_invoice",
			args: { hospitalisation_name: frm.doc.name },
			freeze: true,
			callback(result) {
				const summary = result.message || {};
				frappe.show_alert({
					message: __(`Synced ${summary.added_count || 0} charge item(s) to invoice.`),
					indicator: "green",
				});
				frm.reload_doc();
			},
		});
	}, __("Billing"));
}

function add_hospitalisation_action_buttons(frm) {
	if (frm.is_new()) {
		return;
	}

	frm.add_custom_button(__("Create / Link Invoice"), () => {
		frappe.call({
			method: "vetedge.services.hospitalisation.create_or_link_hospitalisation_invoice",
			args: { hospitalisation_name: frm.doc.name },
			freeze: true,
			callback(result) {
				if (result.message) {
					frappe.set_route("Form", "Sales Invoice", result.message);
				}
			},
		});
	}, __("Billing"));

	frm.add_custom_button(__("Check Payment Gate"), () => {
		frappe.call({
			method: "vetedge.services.hospitalisation.check_hospitalisation_payment_gate",
			args: { hospitalisation_name: frm.doc.name },
			freeze: true,
			callback(result) {
				const gate = result.message || {};
				if (gate.message) {
					frappe.msgprint({
						message: gate.message,
						indicator: gate.can_proceed ? "green" : "red",
					});
				}
				frm.reload_doc();
			},
		});
	}, __("Billing"));

	if (!["Admitted", "Under Care", "Ready for Discharge", "Discharged", "Cancelled"].includes(frm.doc.status)) {
		frm.add_custom_button(__("Admit"), () => {
			frappe.call({
				method: "vetedge.services.hospitalisation.admit_hospitalisation",
				args: { hospitalisation_name: frm.doc.name },
				freeze: true,
				callback(result) {
					const gate = result.message || {};
					if (gate.message) {
						frappe.msgprint({
							message: gate.message,
							indicator: gate.can_proceed ? "green" : "red",
						});
					}
					frm.reload_doc();
				},
			});
		}, __("Clinical"));
	}

	if (["Admitted", "Under Care", "Ready for Discharge"].includes(frm.doc.status)) {
		frm.add_custom_button(__("Discharge"), () => {
			frappe.prompt(
				[{ fieldname: "discharge_summary", fieldtype: "Text Editor", label: __("Discharge Summary") }],
				(values) => {
					frappe.call({
						method: "vetedge.services.hospitalisation.discharge_hospitalisation",
						args: {
							hospitalisation_name: frm.doc.name,
							discharge_summary: values.discharge_summary,
						},
						freeze: true,
						callback() {
							frm.reload_doc();
						},
					});
				},
				__("Discharge Hospitalisation"),
				__("Discharge")
			);
		}, __("Clinical"));
	}
}
