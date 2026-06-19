frappe.ui.form.on("Veterinary Hospitalisation", {
	refresh(frm) {
		set_discharge_fields_visibility(frm);
		set_location_help(frm);
		set_activity_help(frm);
		add_hospitalisation_action_buttons(frm);
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
