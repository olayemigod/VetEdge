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

		if (!frm.is_new() && frm.doc.status !== "Cancelled") {
			frm.add_custom_button(__("Billing / Payment"), () => {
				if (window.vetedgeBillingModal?.open) {
					window.vetedgeBillingModal.open(frm);
					return;
				}
				frappe.msgprint(__("Billing modal helper is not available. Please refresh the page."));
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
	lab_test_template(frm, cdt, cdn) {
		apply_lab_test_result_metadata(frm, cdt, cdn);
	},
	result_format(frm, cdt, cdn) {
		configure_lab_result_editability(frm, cdt, cdn);
	},
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
	["result_value", "result_unit", "reference_range", "abnormal_flag"].forEach((fieldname) => {
		grid.update_docfield_property(fieldname, "depends_on", "eval:['Value Driven', 'Mixed'].includes(doc.result_format)");
	});
	grid.update_docfield_property("result_text", "depends_on", "eval:['Text / Narrative', 'Mixed'].includes(doc.result_format)");
	grid.update_docfield_property("result_attachment", "depends_on", "eval:['Document Upload', 'Mixed'].includes(doc.result_format)");
	frm.refresh_field("lab_tests");
}

function apply_lab_test_result_metadata(frm, cdt, cdn) {
	const row = locals[cdt]?.[cdn];
	if (!row?.lab_test_template) {
		return;
	}

	frappe.db
		.get_value("Veterinary Lab Test", row.lab_test_template, [
			"result_format",
			"result_unit",
			"reference_range",
			"requires_document_upload",
			"allows_manual_result_entry",
			"allows_doctor_result_entry",
			"requires_result_review",
			"sample_type",
			"linked_item",
		])
		.then((result) => {
			const test = result?.message || {};
			frappe.model.set_value(cdt, cdn, "result_format", test.result_format || "Value Driven");
			frappe.model.set_value(cdt, cdn, "result_unit", test.result_unit || "");
			frappe.model.set_value(cdt, cdn, "reference_range", test.reference_range || "");
			frappe.model.set_value(cdt, cdn, "requires_document_upload", test.requires_document_upload ? 1 : 0);
			frappe.model.set_value(cdt, cdn, "allows_manual_result_entry", test.allows_manual_result_entry === 0 ? 0 : 1);
			frappe.model.set_value(cdt, cdn, "allows_doctor_result_entry", test.allows_doctor_result_entry === 0 ? 0 : 1);
			frappe.model.set_value(cdt, cdn, "requires_result_review", test.requires_result_review === 0 ? 0 : 1);
			if (test.sample_type && !row.sample_type) {
				frappe.model.set_value(cdt, cdn, "sample_type", test.sample_type);
			}
			if (test.linked_item && !row.billing_item) {
				frappe.model.set_value(cdt, cdn, "billing_item", test.linked_item);
			}
			configure_lab_result_editability(frm, cdt, cdn);
		});
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
			{
				fieldname: "result_format",
				fieldtype: "Select",
				label: __("Result Format"),
				options: "Value Driven\nText / Narrative\nDocument Upload\nMixed",
				default: "Value Driven",
			},
			{ fieldname: "result_unit", fieldtype: "Data", label: __("Result Unit") },
			{ fieldname: "reference_range", fieldtype: "Small Text", label: __("Reference Range") },
			{ fieldname: "requires_document_upload", fieldtype: "Check", label: __("Requires Document Upload") },
			{ fieldname: "allows_manual_result_entry", fieldtype: "Check", label: __("Allows Manual Result Entry"), default: 1 },
			{ fieldname: "allows_doctor_result_entry", fieldtype: "Check", label: __("Allows Doctor Result Entry"), default: 1 },
			{ fieldname: "requires_result_review", fieldtype: "Check", label: __("Requires Result Review"), default: 1 },
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
