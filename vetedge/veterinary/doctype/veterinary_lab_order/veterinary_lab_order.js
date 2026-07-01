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
		render_lab_tests_workbench(frm);

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

	lab_tests_add(frm) {
		render_lab_tests_workbench(frm);
	},

	lab_tests_remove(frm) {
		render_lab_tests_workbench(frm);
	},
});

frappe.ui.form.on("Veterinary Lab Order Item", {
	lab_test_template(frm, cdt, cdn) {
		apply_lab_test_result_metadata(frm, cdt, cdn);
	},
	result_format(frm, cdt, cdn) {
		configure_lab_result_editability(frm, cdt, cdn);
		render_lab_tests_workbench(frm);
	},
	result_value(frm) {
		render_lab_tests_workbench(frm);
	},
	result_text(frm) {
		render_lab_tests_workbench(frm);
	},
	result_attachment(frm) {
		render_lab_tests_workbench(frm);
	},
	rate(frm) {
		render_lab_tests_workbench(frm);
	},
	form_render(frm, cdt, cdn) {
		configure_lab_result_editability(frm, cdt, cdn);
		render_lab_tests_workbench(frm);
	},
	lab_tests_on_form_rendered(frm, cdt, cdn) {
		configure_lab_result_editability(frm, cdt, cdn);
		render_lab_tests_workbench(frm);
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
			"default_rate",
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
			if (test.default_rate !== undefined && test.default_rate !== null && [undefined, null, ""].includes(row.rate)) {
				frappe.model.set_value(cdt, cdn, "rate", test.default_rate);
			}
			if (!row.billing_status) {
				frappe.model.set_value(cdt, cdn, "billing_status", frm.doc.linked_invoice ? "Invoice Linked" : "Not Billed");
			}
			frappe.model.set_value(cdt, cdn, "result_action", "Result Actions");
			configure_lab_result_editability(frm, cdt, cdn);
			render_lab_tests_workbench(frm);
		});
}

function add_creation_actions(frm) {
	frm.add_custom_button(__("Add Lab Tests"), () => {
		show_add_lab_tests_dialog(frm);
	}, __("Clinical"));

	frm.add_custom_button(__("New Lab Test"), () => {
		show_lab_test_dialog(frm);
	}, __("Clinical"));
}

function show_add_lab_tests_dialog(frm) {
	frappe.call({
		method: "vetedge.services.lab.get_active_lab_tests_for_picker",
		freeze: true,
		freeze_message: __("Loading lab tests..."),
		callback(response) {
			const tests = response.message || [];
			const selected = {};
			const dialog = new frappe.ui.Dialog({
				title: __("Add Lab Tests"),
				fields: [
					{ fieldname: "search", fieldtype: "Data", label: __("Search") },
					{ fieldname: "tests_html", fieldtype: "HTML" },
				],
				primary_action_label: __("Add Selected"),
				primary_action() {
					add_selected_lab_tests(frm, tests, selected);
					dialog.hide();
				},
			});

			const render = () => render_lab_test_picker(dialog, tests, selected);
			dialog.fields_dict.search.$input.on("input", render);
			dialog.show();
			render();
		},
	});
}

function render_lab_test_picker(dialog, tests, selected) {
	const query = (dialog.get_value("search") || "").toLowerCase();
	const rows = tests.filter((test) => {
		const haystack = [test.name, test.test_name, test.sample_type, test.result_format].join(" ").toLowerCase();
		return !query || haystack.includes(query);
	});
	const html = `
		<div class="table-responsive">
			<table class="table table-bordered table-hover table-sm">
				<thead>
					<tr>
						<th style="width: 32px;"></th>
						<th>${__("Lab Test")}</th>
						<th>${__("Result Format")}</th>
						<th>${__("Sample Type")}</th>
						<th style="width: 120px;">${__("Rate")}</th>
					</tr>
				</thead>
				<tbody>
					${rows.map((test) => render_lab_test_picker_row(test, selected)).join("") || `<tr><td colspan="5" class="text-muted">${__("No lab tests found")}</td></tr>`}
				</tbody>
			</table>
		</div>
	`;
	dialog.fields_dict.tests_html.$wrapper.html(html);
	dialog.fields_dict.tests_html.$wrapper.find("[data-lab-test]").on("change", (event) => {
		const name = event.currentTarget.dataset.labTest;
		if (event.currentTarget.checked) {
			selected[name] = {
				name,
				rate: dialog.fields_dict.tests_html.$wrapper.find("[data-rate-for]").filter((_, input) => input.dataset.rateFor === name).val(),
			};
		} else {
			delete selected[name];
		}
	});
	dialog.fields_dict.tests_html.$wrapper.find("[data-rate-for]").on("input", (event) => {
		const name = event.currentTarget.dataset.rateFor;
		if (selected[name]) {
			selected[name].rate = event.currentTarget.value;
		}
	});
}

function render_lab_test_picker_row(test, selected) {
	const name = escape_html(test.name || "");
	const label = escape_html(test.test_name || test.name || "");
	const sampleType = escape_html(test.sample_type || "");
	const resultFormat = escape_html(test.result_format || "Value Driven");
	const rate = test.default_rate ?? "";
	const checked = selected[test.name] ? "checked" : "";
	return `
		<tr>
			<td><input type="checkbox" data-lab-test="${name}" ${checked}></td>
			<td>${label}<div class="text-muted small">${name}</div></td>
			<td>${resultFormat}</td>
			<td>${sampleType}</td>
			<td><input class="form-control input-xs" type="number" step="0.01" data-rate-for="${name}" value="${escape_html(String(selected[test.name]?.rate ?? rate))}"></td>
		</tr>
	`;
}

function add_selected_lab_tests(frm, tests, selected) {
	const existing = new Set((frm.doc.lab_tests || []).map((row) => row.lab_test_template));
	const byName = Object.fromEntries(tests.map((test) => [test.name, test]));
	Object.keys(selected).forEach((name) => {
		if (existing.has(name) || !byName[name]) {
			return;
		}
		const test = byName[name];
		const row = frm.add_child("lab_tests");
		row.lab_test_template = test.name;
		row.lab_test_name = test.test_name;
		row.sample_type = test.sample_type;
		row.billing_item = test.linked_item;
		row.rate = selected[name].rate || test.default_rate || 0;
		row.billing_status = frm.doc.linked_invoice ? "Invoice Linked" : "Not Billed";
		row.status = frm.doc.status && frm.doc.status !== "Draft" ? frm.doc.status : "Requested";
		row.result_format = test.result_format || "Value Driven";
		row.result_unit = test.result_unit;
		row.reference_range = test.reference_range;
		row.requires_document_upload = test.requires_document_upload ? 1 : 0;
		row.allows_manual_result_entry = test.allows_manual_result_entry === 0 ? 0 : 1;
		row.allows_doctor_result_entry = test.allows_doctor_result_entry === 0 ? 0 : 1;
		row.requires_result_review = test.requires_result_review === 0 ? 0 : 1;
		row.result_status = "Pending";
		row.result_action = "Result Actions";
	});
	frm.refresh_field("lab_tests");
	render_lab_tests_workbench(frm);
}

function render_lab_tests_workbench(frm) {
	const wrapper = frm.fields_dict.lab_tests_workbench?.$wrapper;
	if (!wrapper) {
		return;
	}
	const rows = frm.doc.lab_tests || [];
	if (!rows.length) {
		wrapper.html(`<div class="text-muted">${__("No lab tests added yet.")}</div>`);
		return;
	}
	const html = `
		<div class="table-responsive vetedge-lab-tests-workbench">
			<table class="table table-bordered table-hover table-sm">
				<thead>
					<tr>
						<th>${__("Lab Test")}</th>
						<th>${__("Result Format")}</th>
						<th style="width: 100px;">${__("Rate")}</th>
						<th>${__("Billing Status")}</th>
						<th>${__("Result Status")}</th>
						<th>${__("Result Summary")}</th>
						<th style="width: 230px;">${__("Action")}</th>
					</tr>
				</thead>
				<tbody>
					${rows.map((row) => render_lab_order_item_workbench_row(frm, row)).join("")}
				</tbody>
			</table>
		</div>
	`;
	wrapper.html(html);
	wrapper.find("[data-lab-result-action]").on("click", (event) => {
		const action = event.currentTarget.dataset.labResultAction;
		const rowName = event.currentTarget.dataset.rowName;
		const row = (frm.doc.lab_tests || []).find((item) => item.name === rowName);
		if (!row) {
			return;
		}
		if (action === "view") {
			show_view_result_dialog(row);
		} else if (action === "review") {
			show_review_result_dialog(frm, row);
		} else {
			show_post_result_dialog(frm, row);
		}
	});
	wrapper.find("[data-lab-rate]").on("change", (event) => {
		const rowName = event.currentTarget.dataset.rowName;
		const row = (frm.doc.lab_tests || []).find((item) => item.name === rowName);
		if (!row) {
			return;
		}
		update_lab_order_item_rate(frm, row, event.currentTarget.value);
	});
}

function render_lab_order_item_workbench_row(frm, row) {
	const rowName = escape_html(row.name || "");
	const label = escape_html(row.lab_test_name || row.lab_test_template || "");
	const template = escape_html(row.lab_test_template || "");
	const resultFormat = escape_html(row.result_format || "Value Driven");
	const rate = row.rate ?? "";
	const rateCell = can_edit_lab_order_item_rate(frm, row)
		? `<input class="form-control input-xs" type="number" step="0.01" min="0" data-lab-rate data-row-name="${rowName}" value="${escape_html(String(rate))}">`
		: escape_html(String(rate));
	const billingStatus = escape_html(row.billing_status || "Not Billed");
	const resultStatus = escape_html(row.result_status || "Pending");
	const summary = escape_html(get_lab_result_summary(row));
	const resultActions = render_lab_result_action_buttons(rowName, row);
	return `
		<tr>
			<td>${label}<div class="text-muted small">${template}</div></td>
			<td>${resultFormat}</td>
			<td>${rateCell}</td>
			<td>${billingStatus}</td>
			<td>${resultStatus}</td>
			<td>${summary || `<span class="text-muted">${__("Pending")}</span>`}</td>
			<td>${resultActions}</td>
		</tr>
	`;
}

function render_lab_result_action_buttons(rowName, row) {
	const locked = ["Reviewed", "Cancelled"].includes(row.status) || ["Reviewed"].includes(row.result_status);
	const hasResult = has_lab_result_content(row);
	const buttons = [];
	if (!locked) {
		buttons.push(
			`<button type="button" class="btn btn-xs btn-default" data-lab-result-action="post" data-row-name="${rowName}">${hasResult ? __("Update Result") : __("Post / Upload Result")}</button>`
		);
	}
	if (hasResult) {
		buttons.push(`<button type="button" class="btn btn-xs btn-default" data-lab-result-action="view" data-row-name="${rowName}">${__("View Result")}</button>`);
	}
	if (!locked && hasResult && row.requires_result_review) {
		buttons.push(`<button type="button" class="btn btn-xs btn-primary" data-lab-result-action="review" data-row-name="${rowName}">${__("Review Result")}</button>`);
	}
	return buttons.join(" ");
}

function show_post_result_dialog(frm, row) {
	const resultFormat = row.result_format || "Value Driven";
	const fields = [];
	if (["Value Driven", "Mixed"].includes(resultFormat)) {
		fields.push(
			{ fieldname: "result_value", fieldtype: "Data", label: __("Result Value"), default: row.result_value },
			{ fieldname: "result_unit", fieldtype: "Data", label: __("Unit"), default: row.result_unit },
			{ fieldname: "reference_range", fieldtype: "Small Text", label: __("Reference Range"), default: row.reference_range },
			{ fieldname: "abnormal_flag", fieldtype: "Check", label: __("Abnormal"), default: row.abnormal_flag ? 1 : 0 },
		);
	}
	if (["Text / Narrative", "Mixed"].includes(resultFormat)) {
		fields.push({ fieldname: "result_text", fieldtype: "Text", label: __("Narrative Result"), default: row.result_text });
	}
	if (["Document Upload", "Mixed"].includes(resultFormat)) {
		fields.push({ fieldname: "result_attachment", fieldtype: "Attach", label: __("Result Attachment"), default: row.result_attachment });
	}
	fields.push({ fieldname: "remarks", fieldtype: "Small Text", label: __("Result Note"), default: row.remarks });

	const dialog = new frappe.ui.Dialog({
		title: has_lab_result_content(row) ? __("Update Result") : __("Post / Upload Result"),
		fields,
		primary_action_label: __("Save Result"),
		primary_action(values) {
			apply_lab_result_values(frm, row, values);
			dialog.hide();
		},
	});
	dialog.show();
}

function can_edit_lab_order_item_rate(frm, row) {
	if (["Reviewed", "Cancelled"].includes(frm.doc.status) || ["Reviewed", "Cancelled"].includes(row.status)) {
		return false;
	}
	if (["Submitted Invoiced", "Paid", "Cancelled"].includes(row.billing_status)) {
		return false;
	}
	return !frm.is_new();
}

function update_lab_order_item_rate(frm, row, value) {
	const childDoctype = row.doctype || "Veterinary Lab Order Item";
	const rate = flt(value);
	frappe.model.set_value(childDoctype, row.name, "rate", rate).then(() => {
		frm.refresh_field("lab_tests");
		render_lab_tests_workbench(frm);
		frm.save_or_update();
	});
}

function apply_lab_result_values(frm, row, values) {
	const childDoctype = row.doctype || "Veterinary Lab Order Item";
	const setters = Object.keys(values).map((fieldname) =>
		frappe.model.set_value(childDoctype, row.name, fieldname, values[fieldname])
	);
	Promise.all(setters).then(() => {
		const updated = locals[childDoctype]?.[row.name] || row;
		frappe.model.set_value(childDoctype, row.name, "result_status", "Entered");
		frappe.model.set_value(childDoctype, row.name, "status", "Result Entered");
		frappe.model.set_value(childDoctype, row.name, "result_summary", get_lab_result_summary(updated));
		frappe.model.set_value(childDoctype, row.name, "result_action", "Result Actions");
		if (!["Result Entered", "Reviewed", "Cancelled"].includes(frm.doc.status)) {
			frm.set_value("status", "Result Entered");
		}
		frm.refresh_field("lab_tests");
		render_lab_tests_workbench(frm);
		frm.save_or_update();
	});
}

function show_view_result_dialog(row) {
	const dialog = new frappe.ui.Dialog({
		title: __("View Result"),
		fields: [
			{ fieldname: "lab_test", fieldtype: "Data", label: __("Lab Test"), default: row.lab_test_name || row.lab_test_template, read_only: 1 },
			{ fieldname: "result_format", fieldtype: "Data", label: __("Result Format"), default: row.result_format, read_only: 1 },
			{ fieldname: "result_summary", fieldtype: "Small Text", label: __("Result Summary"), default: get_lab_result_summary(row), read_only: 1 },
			{ fieldname: "result_attachment", fieldtype: "Attach", label: __("Result Attachment"), default: row.result_attachment, read_only: 1 },
			{ fieldname: "remarks", fieldtype: "Small Text", label: __("Result Note"), default: row.remarks, read_only: 1 },
		],
	});
	dialog.show();
}

function show_review_result_dialog(frm, row) {
	const dialog = new frappe.ui.Dialog({
		title: __("Review Result"),
		fields: [
			{ fieldname: "lab_test", fieldtype: "Data", label: __("Lab Test"), default: row.lab_test_name || row.lab_test_template, read_only: 1 },
			{ fieldname: "result_summary", fieldtype: "Small Text", label: __("Result Summary"), default: get_lab_result_summary(row), read_only: 1 },
			{ fieldname: "review_note", fieldtype: "Small Text", label: __("Review Note") },
		],
		primary_action_label: __("Mark Reviewed"),
		primary_action(values) {
			const childDoctype = row.doctype || "Veterinary Lab Order Item";
			if (values.review_note) {
				frappe.model.set_value(childDoctype, row.name, "remarks", values.review_note);
			}
			frappe.model.set_value(childDoctype, row.name, "result_status", "Reviewed");
			frappe.model.set_value(childDoctype, row.name, "status", "Reviewed");
			frm.set_value("status", "Reviewed");
			frm.set_value("doctor_reviewed_by", frappe.session.user);
			frm.set_value("doctor_reviewed_on", frappe.datetime.now_datetime());
			frm.refresh_field("lab_tests");
			render_lab_tests_workbench(frm);
			dialog.hide();
			frm.save_or_update();
		},
	});
	dialog.show();
}

function get_lab_result_summary(row) {
	const parts = [];
	if (![undefined, null, ""].includes(row.result_value)) {
		parts.push([row.result_value, row.result_unit].filter(Boolean).join(" "));
	}
	if (row.result_text) {
		parts.push(row.result_text.length > 80 ? `${row.result_text.slice(0, 77)}...` : row.result_text);
	}
	if (row.result_attachment) {
		parts.push(__("Document uploaded"));
	}
	if (row.abnormal_flag) {
		parts.push(__("Abnormal"));
	}
	const summary = parts.filter(Boolean).join(" | ");
	return summary || row.result_summary || "";
}

function has_lab_result_content(row) {
	return Boolean(row.result_value || row.result_text || row.result_attachment || row.remarks);
}

function escape_html(value) {
	if (frappe.utils?.escape_html) {
		return frappe.utils.escape_html(value);
	}
	return String(value ?? "")
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;")
		.replace(/'/g, "&#039;");
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
