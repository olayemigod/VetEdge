frappe.ui.form.on("Veterinary Lab Order", {
	setup(frm) {
		frm.set_query("patient", () => ({
			filters: {
				status: ["!=", "Deceased"],
			},
		}));

		frm.set_query("consultation", () => ({
			filters: {
				patient: frm.doc.patient,
			},
		}));

		frm.set_query("lab_test_template", "lab_tests", () => ({
			filters: {
				is_active: 1,
			},
		}));

		frm.set_query("billing_item", "lab_tests", () => ({
			filters: {
				disabled: 0,
				is_sales_item: 1,
			},
		}));
	},

	refresh(frm) {
		add_creation_actions(frm);
		configure_lab_result_editability(frm);

		if (!frm.is_new() && frm.doc.consultation) {
			frm.add_custom_button(__("Open Consultation"), () => {
				frappe.set_route("Form", "Veterinary Consultation", frm.doc.consultation);
			}, __("Clinical"));
		}

		if (!frm.is_new() && frm.doc.linked_invoice) {
			frm.add_custom_button(__("Open Invoice"), () => {
				vetedgeInvoiceSummary.open(frm.doc.linked_invoice);
			}, __("Billing"));
		} else if (!frm.is_new() && !frm.doc.consultation) {
			frm.add_custom_button(__("Create Invoice"), () => {
				frappe.call({
					method: "vetedge.services.lab.create_lab_order_invoice",
					args: {
						lab_order: frm.doc.name,
					},
					freeze: true,
					freeze_message: __("Creating invoice..."),
					callback(result) {
						if (!result.message?.invoice) {
							return;
						}
						frappe.show_alert({
							message: __("Invoice created"),
							indicator: "green",
						});
					frm.reload_doc();
				},
			});
		}, __("Billing"));
		}

		add_status_actions(frm);
	},

	patient(frm) {
		if (!frm.doc.patient) {
			return;
		}

		frappe.db
			.get_value("Veterinary Patient", frm.doc.patient, ["primary_owner", "default_branch"])
			.then((result) => {
			const patient = result?.message || {};
			if (!frm.doc.primary_owner && patient.primary_owner) {
				frm.set_value("primary_owner", patient.primary_owner);
			}
			if (!frm.doc.service_branch && patient.default_branch) {
				frm.set_value("service_branch", patient.default_branch);
				}
			});
	},

	consultation(frm) {
		if (!frm.doc.consultation) {
			return;
		}

		frappe.db
			.get_value("Veterinary Consultation", frm.doc.consultation, [
				"patient",
				"primary_owner",
				"service_branch",
			])
			.then((result) => {
			const consultation = result?.message || {};
			if (consultation.patient && !frm.doc.patient) {
				frm.set_value("patient", consultation.patient);
			}
			if (consultation.primary_owner && !frm.doc.primary_owner) {
				frm.set_value("primary_owner", consultation.primary_owner);
			}
			if (consultation.service_branch && !frm.doc.service_branch) {
				frm.set_value("service_branch", consultation.service_branch);
				}
			});
	},
});

frappe.ui.form.on("Veterinary Lab Order Item", {
	form_render(frm, cdt, cdn) {
		configure_lab_result_editability(frm, cdt, cdn);
	},
	lab_tests_on_form_rendered(frm, cdt, cdn) {
		configure_lab_result_editability(frm, cdt, cdn);
	},
});

function configure_lab_result_editability(frm, cdt = null, cdn = null) {
	const grid = frm.get_field("lab_tests")?.grid;
	if (!grid) {
		return;
	}

	const orderLocked = ["Reviewed", "Cancelled"].includes(frm.doc.status);
	frm.set_df_property("lab_tests", "read_only", orderLocked ? 1 : 0);
	frm.refresh_field("lab_tests");
}

function add_creation_actions(frm) {
	frm.add_custom_button(__("New Lab Test"), () => {
		show_lab_test_dialog(frm);
	}, __("Clinical"));
}

function show_lab_test_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("New Lab Test"),
		fields: [
			{ fieldname: "test_name", fieldtype: "Data", label: __("Test Name"), reqd: 1 },
			{ fieldname: "test_code", fieldtype: "Data", label: __("Test Code") },
			{
				fieldname: "sample_type",
				fieldtype: "Select",
				label: __("Sample Type"),
				options: "\nBlood\nSerum\nPlasma\nUrine\nFeces\nSwab\nTissue\nOther",
			},
			{ fieldname: "linked_item", fieldtype: "Link", label: __("Linked Billing Item"), options: "Item" },
			{ fieldname: "default_rate", fieldtype: "Currency", label: __("Default Rate") },
			{ fieldname: "description", fieldtype: "Small Text", label: __("Description") },
		],
		primary_action_label: __("Create Lab Test"),
		primary_action(values) {
			frappe.call({
				method: "vetedge.services.lab.create_lab_test_from_dialog",
				args: { values },
				freeze: true,
				freeze_message: __("Creating lab test..."),
				callback(result) {
					if (!result.message?.name) {
						return;
					}
					dialog.hide();
					frappe.show_alert({
						message: __("Lab test created"),
						indicator: "green",
					});
					frm.reload_doc();
				},
			});
		},
	});

	dialog.show();
}

function add_status_actions(frm) {
	if (frm.is_new() || ["Reviewed", "Cancelled"].includes(frm.doc.status)) {
		return;
	}

	const transitions = {
		Draft: [[__("Request Lab Tests"), "Requested"]],
		Requested: [
			[__("Mark Sample Collected"), "Sample Collected"],
			[__("Start Processing"), "In Progress"],
			[__("Cancel Lab Order"), "Cancelled"],
		],
		"Sample Collected": [
			[__("Start Processing"), "In Progress"],
			[__("Cancel Lab Order"), "Cancelled"],
		],
		"In Progress": [
			[__("Mark Result Entered"), "Result Entered"],
			[__("Cancel Lab Order"), "Cancelled"],
		],
		"Result Entered": [
			[__("Mark Reviewed"), "Reviewed"],
			[__("Cancel Lab Order"), "Cancelled"],
		],
	};

	(transitions[frm.doc.status] || []).forEach(([label, status]) => {
		frm.add_custom_button(label, () => {
			frappe.call({
				method: "vetedge.services.lab.transition_lab_order_status",
				args: {
					lab_order: frm.doc.name,
					status,
				},
				freeze: true,
				freeze_message: __("Updating lab order..."),
				callback() {
					frappe.show_alert({
						message: __("Lab order updated"),
						indicator: "green",
					});
					frm.reload_doc();
				},
			});
		}, __("Status"));
	});
}
