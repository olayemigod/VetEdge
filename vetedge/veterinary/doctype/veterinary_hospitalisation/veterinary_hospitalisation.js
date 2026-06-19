frappe.ui.form.on("Veterinary Hospitalisation", {
	refresh(frm) {
		set_discharge_fields_visibility(frm);
		set_location_help(frm);
		set_activity_help(frm);
		add_hospitalisation_action_buttons(frm);
		add_activity_dialog_button(frm);
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


function add_activity_dialog_button(frm) {
	if (frm.is_new() || ["Cancelled", "Discharged"].includes(frm.doc.status)) {
		return;
	}

	frm.add_custom_button(__("Add Activity"), () => {
		open_activity_dialog(frm);
	}, __("Clinical"));
}

function open_activity_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Add Hospitalisation Activity"),
		fields: [
			{
				fieldname: "activity_intro",
				fieldtype: "HTML",
				options: `<p class="text-muted">${__(
					"Record clinical activity first. Billing and stock posting are handled separately."
				)}</p>`,
			},
			{
				fieldname: "activity_type",
				fieldtype: "Select",
				label: __("Activity Type"),
				reqd: 1,
				options: [
					"Vitals",
					"Medication",
					"Vaccination",
					"Fluid Therapy",
					"Feeding",
					"Nursing Note",
					"Wound Care",
					"Lab",
					"Imaging",
					"Procedure",
					"Oxygen / Nebulisation",
					"Owner Communication",
					"Other",
				].join("\n"),
			},
			{
				fieldname: "activity_datetime",
				fieldtype: "Datetime",
				label: __("Activity Datetime"),
				default: frappe.datetime.now_datetime(),
			},
			{
				fieldname: "performed_by",
				fieldtype: "Link",
				label: __("Performed By"),
				options: "User",
				default: frappe.session.user,
			},
			{
				fieldname: "clinical_notes",
				fieldtype: "Text Editor",
				label: __("Clinical Notes"),
			},
			{
				fieldname: "flags_section",
				fieldtype: "Section Break",
			},
			{
				fieldname: "billable",
				fieldtype: "Check",
				label: __("Billable"),
				onchange: () => update_activity_dialog_item_visibility(dialog),
			},
			{
				fieldname: "stock_affecting",
				fieldtype: "Check",
				label: __("Stock Affecting"),
				onchange: () => update_activity_dialog_item_visibility(dialog),
			},
			{
				fieldname: "item_section",
				fieldtype: "Section Break",
				depends_on: "eval:doc.billable || doc.stock_affecting",
			},
			{
				fieldname: "item",
				fieldtype: "Link",
				label: __("Item"),
				options: "Item",
				onchange: () => set_default_activity_qty(dialog),
				depends_on: "eval:doc.billable || doc.stock_affecting",
			},
			{
				fieldname: "qty",
				fieldtype: "Float",
				label: __("Qty"),
				default: 1,
				depends_on: "eval:doc.billable || doc.stock_affecting",
			},
			{
				fieldname: "uom",
				fieldtype: "Link",
				label: __("UOM"),
				options: "UOM",
				depends_on: "eval:doc.billable || doc.stock_affecting",
			},
		],
		primary_action_label: __("Add"),
		primary_action(values) {
			add_activity_row_from_dialog(frm, dialog, values);
		},
	});

	update_activity_dialog_item_visibility(dialog);
	dialog.show();
}

function update_activity_dialog_item_visibility(dialog) {
	const values = dialog.get_values(true) || {};
	const show_item_fields = Boolean(values.billable || values.stock_affecting);
	["item_section", "item", "qty", "uom"].forEach((fieldname) => {
		dialog.set_df_property(fieldname, "hidden", !show_item_fields);
	});
	dialog.refresh();
}

function set_default_activity_qty(dialog) {
	const values = dialog.get_values(true) || {};
	if (values.item && !values.qty) {
		dialog.set_value("qty", 1);
	}
}

function add_activity_row_from_dialog(frm, dialog, values) {
	if (!values.item && values.billable) {
		frappe.show_alert({
			message: __("Charge sheet sync requires an Item for billable activities."),
			indicator: "orange",
		});
	}
	if (!values.item && values.stock_affecting) {
		frappe.show_alert({
			message: __("Stock posting will require an Item when it is enabled."),
			indicator: "orange",
		});
	}

	const row = frm.add_child("activities");
	row.activity_type = values.activity_type;
	row.activity_datetime = values.activity_datetime;
	row.performed_by = values.performed_by;
	row.clinical_notes = values.clinical_notes;
	row.billable = values.billable ? 1 : 0;
	row.stock_affecting = values.stock_affecting ? 1 : 0;
	row.item = values.item;
	row.qty = values.item && !values.qty ? 1 : values.qty;
	row.uom = values.uom;
	row.billing_status = values.billable ? "Pending Charge" : "Not Billable";
	row.stock_status = values.stock_affecting ? "Pending" : "Not Applicable";

	frm.refresh_field("activities");
	frm.dirty();
	dialog.hide();
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

	frm.add_custom_button(__("Billing / Payment"), () => {
		if (window.vetedgeBillingModal?.open) {
			window.vetedgeBillingModal.open(frm);
			return;
		}
		frappe.msgprint(__("Billing modal helper is not available. Please refresh the page."));
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
