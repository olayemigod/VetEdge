frappe.ui.form.on("Veterinary Hospitalisation", {
	refresh(frm) {
		set_discharge_fields_visibility(frm);
		set_location_help(frm);
		set_activity_help(frm);
		add_hospitalisation_action_buttons(frm);
		add_clinical_activity_action_buttons(frm);
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



function add_clinical_activity_action_buttons(frm) {
	if (frm.is_new() || ["Cancelled", "Discharged"].includes(frm.doc.status)) {
		return;
	}

	[
		["Add Vitals", () => open_hospitalisation_vitals_dialog(frm)],
		["Add Vaccination", () => open_hospitalisation_vaccination_dialog(frm)],
		["Add Lab Order", () => open_hospitalisation_lab_order_dialog(frm)],
		["Add Medication", () => open_activity_dialog(frm, { activity_type: "Medication", title: "Add Medication" })],
		["Add Fluid Therapy", () => open_activity_dialog(frm, { activity_type: "Fluid Therapy", title: "Add Fluid Therapy" })],
		["Add Feeding", () => open_activity_dialog(frm, { activity_type: "Feeding", title: "Add Feeding" })],
		["Add Nursing Note", () => open_activity_dialog(frm, { activity_type: "Nursing Note", title: "Add Nursing Note" })],
		["Add Wound Care", () => open_activity_dialog(frm, { activity_type: "Wound Care", title: "Add Wound Care" })],
		["Add Procedure", () => open_activity_dialog(frm, { activity_type: "Procedure", title: "Add Procedure" })],
		["Add Oxygen / Nebulisation", () => open_activity_dialog(frm, { activity_type: "Oxygen / Nebulisation", title: "Add Oxygen / Nebulisation" })],
		["Add Owner Update", () => open_activity_dialog(frm, { activity_type: "Owner Communication", title: "Add Owner Update" })],
		["Add Other Activity", () => open_activity_dialog(frm, { activity_type: "Other", title: "Add Other Activity" })],
	].forEach(([label, action]) => {
		frm.add_custom_button(__(label), action, __("Clinical"));
	});
}

function open_activity_dialog(frm, options = {}) {
	const activityType = options.activity_type || "Other";
	const dialog = new frappe.ui.Dialog({
		title: __(options.title || `Add ${activityType}`),
		fields: get_activity_dialog_fields(activityType),
		primary_action_label: __("Add"),
		primary_action(values) {
			add_activity_row_from_dialog(frm, dialog, {
				...values,
				activity_type: activityType,
				linked_doctype: options.linked_doctype,
				linked_document: options.linked_document,
			});
		},
	});

	update_activity_dialog_item_visibility(dialog);
	dialog.show();
}

function get_activity_dialog_fields(activityType) {
	return [
		{
			fieldname: "activity_intro",
			fieldtype: "HTML",
			options: `<p class="text-muted">${__(
				"Record clinical activity first. Billing and stock posting are handled separately."
			)}</p>`,
		},
		{
			fieldname: "activity_type_display",
			fieldtype: "Data",
			label: __("Activity Type"),
			default: __(activityType),
			read_only: 1,
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
			onchange: function () {
				update_activity_dialog_item_visibility(this.layout);
			},
		},
		{
			fieldname: "stock_affecting",
			fieldtype: "Check",
			label: __("Stock Affecting"),
			onchange: function () {
				update_activity_dialog_item_visibility(this.layout);
			},
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
			onchange: function () {
				set_default_activity_qty(this.layout);
			},
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
	];
}

function open_hospitalisation_vitals_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Add Vitals"),
		fields: [
			{ fieldname: "recorded_on", fieldtype: "Datetime", label: __("Recorded On"), default: frappe.datetime.now_datetime(), reqd: 1 },
			{ fieldname: "vitals_section", fieldtype: "Section Break", label: __("Vitals") },
			{ fieldname: "temperature", fieldtype: "Float", label: __("Temperature") },
			{ fieldname: "weight", fieldtype: "Float", label: __("Weight") },
			{ fieldname: "heart_rate", fieldtype: "Int", label: __("Heart Rate") },
			{ fieldname: "respiratory_rate", fieldtype: "Int", label: __("Respiratory Rate") },
			{ fieldname: "column_break_vitals", fieldtype: "Column Break" },
			{ fieldname: "body_condition_score", fieldtype: "Select", label: __("Body Condition Score"), options: "\n1\n2\n3\n4\n5\n6\n7\n8\n9" },
			{ fieldname: "hydration_status", fieldtype: "Select", label: __("Hydration Status"), options: "\nNormal\nMild Dehydration\nModerate Dehydration\nSevere Dehydration" },
			{ fieldname: "mucous_membrane", fieldtype: "Select", label: __("Mucous Membrane"), options: "\nPink\nPale\nIcteric\nCyanotic\nCongested" },
			{ fieldname: "capillary_refill_time", fieldtype: "Select", label: __("Capillary Refill Time"), options: "\nLess than 2 seconds\nGreater than 2 seconds" },
			{ fieldname: "pain_score", fieldtype: "Select", label: __("Pain Score"), options: "\n0\n1\n2\n3\n4\n5\n6\n7\n8\n9\n10" },
			{ fieldname: "appetite_status", fieldtype: "Select", label: __("Appetite Status"), options: "\nNormal\nReduced\nAbsent\nIncreased\nUnknown" },
			{ fieldname: "notes", fieldtype: "Small Text", label: __("Notes") },
		],
		primary_action_label: __("Add"),
		primary_action(values) {
			if (!frm.doc.linked_consultation) {
				append_activity_row(frm, {
					activity_type: "Vitals",
					activity_datetime: values.recorded_on,
					clinical_notes: format_vitals_activity_notes(values),
				});
				dialog.hide();
				return;
			}
			frappe.call({
				method: "vetedge.services.vitals.create_vitals_from_consultation",
				args: { consultation: frm.doc.linked_consultation, values },
				freeze: true,
				freeze_message: __("Saving vitals..."),
				callback(result) {
					const record = result.message;
					if (!record) {
						return;
					}
					append_activity_row(frm, {
						activity_type: "Vitals",
						activity_datetime: values.recorded_on,
						clinical_notes: format_vitals_activity_notes(values),
						linked_doctype: "Veterinary Vital Signs",
						linked_document: record,
					});
					dialog.hide();
					frappe.show_alert({ message: __("Vitals added"), indicator: "green" });
				},
			});
		},
	});
	dialog.show();
}

function open_hospitalisation_vaccination_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Add Vaccination"),
		fields: [
			{ fieldtype: "Link", fieldname: "vaccine", label: __("Vaccine"), options: "Veterinary Vaccine", reqd: 1 },
			{ fieldtype: "Data", fieldname: "dose", label: __("Dose") },
			{ fieldtype: "Select", fieldname: "route", label: __("Route"), options: "\nOral\nSubcutaneous\nIntramuscular\nIntranasal\nTopical\nOther" },
			{ fieldtype: "Datetime", fieldname: "administered_on", label: __("Administered On"), default: frappe.datetime.now_datetime(), reqd: 1 },
			{ fieldtype: "Date", fieldname: "next_due_date", label: __("Next Due Date") },
			{ fieldtype: "Small Text", fieldname: "notes", label: __("Notes") },
		],
		primary_action_label: __("Add"),
		primary_action(values) {
			if (!frm.doc.linked_consultation) {
				append_activity_row(frm, {
					activity_type: "Vaccination",
					activity_datetime: values.administered_on,
					clinical_notes: format_vaccination_activity_notes(values),
				});
				dialog.hide();
				return;
			}
			frappe.call({
				method: "vetedge.services.vaccination.create_vaccination_from_consultation",
				args: { consultation: frm.doc.linked_consultation, values, create_invoice: 0, post_stock: 0 },
				freeze: true,
				freeze_message: __("Saving vaccination..."),
				callback(response) {
					const record = response.message;
					if (!record?.name) {
						return;
					}
					append_activity_row(frm, {
						activity_type: "Vaccination",
						activity_datetime: values.administered_on,
						clinical_notes: format_vaccination_activity_notes(values),
						linked_doctype: "Veterinary Vaccination Record",
						linked_document: record.name,
					});
					dialog.hide();
					frappe.show_alert({ message: __("Vaccination added"), indicator: "green" });
				},
			});
		},
	});
	dialog.show();
}

function open_hospitalisation_lab_order_dialog(frm) {
	if (!frm.doc.linked_consultation) {
		open_activity_dialog(frm, { activity_type: "Lab", title: "Add Lab Order" });
		return;
	}

	frappe.call({
		method: "vetedge.services.lab.get_active_lab_tests_for_picker",
		callback(result) {
			const tests = result.message || [];
			const state = { selected: [] };
			const dialog = new frappe.ui.Dialog({
				title: __("Add Lab Order"),
				fields: [
					{ fieldname: "sample_notes", fieldtype: "Small Text", label: __("Sample Notes") },
					{ fieldname: "search_text", fieldtype: "Data", label: __("Search Lab Tests"), change() { render_hospitalisation_lab_test_picker(dialog, tests, state); } },
					{ fieldname: "selected_html", fieldtype: "HTML" },
					{ fieldname: "results_html", fieldtype: "HTML" },
				],
				primary_action_label: __("Create Lab Order"),
				primary_action(values) {
					if (!state.selected.length) {
						frappe.msgprint(__("Please select at least one lab test."));
						return;
					}
					frappe.call({
						method: "vetedge.services.lab.create_lab_order_from_consultation",
						args: {
							consultation: frm.doc.linked_consultation,
							sample_notes: values.sample_notes,
							lab_tests: state.selected.map((name) => ({ lab_test_template: name })),
						},
						freeze: true,
						freeze_message: __("Creating lab order..."),
						callback(response) {
							const order = response.message;
							if (!order?.name) {
								return;
							}
							append_activity_row(frm, {
								activity_type: "Lab",
								clinical_notes: values.sample_notes,
								linked_doctype: "Veterinary Lab Order",
								linked_document: order.name,
							});
							dialog.hide();
							frappe.show_alert({ message: __("Lab order added"), indicator: "green" });
						},
					});
				},
			});
			dialog.show();
			render_hospitalisation_lab_test_picker(dialog, tests, state);
		},
	});
}

function render_hospitalisation_lab_test_picker(dialog, tests, state) {
	const searchText = (dialog.get_value("search_text") || "").trim().toLowerCase();
	const available = (tests || []).filter((test) => {
		if (!searchText) {
			return true;
		}
		return [test.name, test.test_name, test.sample_type]
			.filter(Boolean)
			.some((value) => String(value).toLowerCase().includes(searchText));
	});
	const selectedWrapper = dialog.fields_dict.selected_html.$wrapper;
	const resultWrapper = dialog.fields_dict.results_html.$wrapper;
	const selectedTests = state.selected.map((name) => tests.find((test) => test.name === name)).filter(Boolean);

	selectedWrapper.html(selectedTests.length
		? `<div class="small text-muted" style="margin-bottom: 8px;">${__("Selected Lab Tests")}</div><div style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px;">${selectedTests.map((test) => `<span class="indicator-pill blue" data-remove="${frappe.utils.escape_html(test.name)}" style="cursor: pointer;">${frappe.utils.escape_html(test.test_name || test.name)}</span>`).join("")}</div>`
		: `<div class="text-muted small" style="margin-bottom: 12px;">${__("No lab tests selected yet.")}</div>`);

	resultWrapper.html(available.length
		? available.map((test) => {
			const isSelected = state.selected.includes(test.name);
			return `<div class="lab-test-picker-row" data-name="${frappe.utils.escape_html(test.name)}" style="border: 1px solid var(--border-color); border-radius: 10px; padding: 12px; margin-bottom: 10px; cursor: pointer; background: ${isSelected ? "var(--subtle-fg)" : "var(--card-bg)"};"><div style="display: flex; justify-content: space-between; gap: 12px; align-items: center;"><div><div style="font-weight: 600;">${frappe.utils.escape_html(test.test_name || test.name)}</div><div class="text-muted small">${frappe.utils.escape_html(test.sample_type || __("Sample type not set"))}</div></div><div class="small ${isSelected ? "text-primary" : "text-muted"}">${isSelected ? __("Selected") : __("Select")}</div></div></div>`;
		}).join("")
		: `<div class="text-muted small">${__("No matching lab tests found.")}</div>`);

	selectedWrapper.find("[data-remove]").on("click", function () {
		state.selected = state.selected.filter((value) => value !== $(this).attr("data-remove"));
		render_hospitalisation_lab_test_picker(dialog, tests, state);
	});
	resultWrapper.find(".lab-test-picker-row").on("click", function () {
		const name = $(this).attr("data-name");
		state.selected = state.selected.includes(name)
			? state.selected.filter((value) => value !== name)
			: [...state.selected, name];
		render_hospitalisation_lab_test_picker(dialog, tests, state);
	});
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
	append_activity_row(frm, values);
	dialog.hide();
}

function append_activity_row(frm, values) {
	const row = frm.add_child("activities");
	row.activity_type = values.activity_type || "Other";
	row.activity_datetime = values.activity_datetime || frappe.datetime.now_datetime();
	row.performed_by = values.performed_by || frappe.session.user;
	row.clinical_notes = values.clinical_notes;
	row.billable = values.billable ? 1 : 0;
	row.stock_affecting = values.stock_affecting ? 1 : 0;
	row.item = values.item;
	row.qty = values.item && !values.qty ? 1 : values.qty;
	row.uom = values.uom;
	row.linked_doctype = values.linked_doctype;
	row.linked_document = values.linked_document;
	row.billing_status = values.billable ? "Pending Charge" : "Not Billable";
	row.stock_status = values.stock_affecting ? "Pending" : "Not Applicable";

	frm.refresh_field("activities");
	frm.dirty();
}

function format_vitals_activity_notes(values) {
	const parts = [
		[__("Temperature"), values.temperature],
		[__("Weight"), values.weight],
		[__("Heart Rate"), values.heart_rate],
		[__("Respiratory Rate"), values.respiratory_rate],
		[__("Body Condition Score"), values.body_condition_score],
		[__("Hydration"), values.hydration_status],
		[__("Mucous Membrane"), values.mucous_membrane],
		[__("Capillary Refill Time"), values.capillary_refill_time],
		[__("Pain Score"), values.pain_score],
		[__("Appetite"), values.appetite_status],
	].filter((row) => row[1]).map((row) => `${row[0]}: ${row[1]}`);
	if (values.notes) {
		parts.push(values.notes);
	}
	return parts.join("\n");
}

function format_vaccination_activity_notes(values) {
	return [
		values.vaccine ? `${__("Vaccine")}: ${values.vaccine}` : null,
		values.dose ? `${__("Dose")}: ${values.dose}` : null,
		values.route ? `${__("Route")}: ${values.route}` : null,
		values.next_due_date ? `${__("Next Due")}: ${values.next_due_date}` : null,
		values.notes,
	].filter(Boolean).join("\n");
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
