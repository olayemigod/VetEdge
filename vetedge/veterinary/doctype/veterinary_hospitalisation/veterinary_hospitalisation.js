frappe.ui.form.on("Veterinary Hospitalisation", {
	setup(frm) {
		set_attending_veterinarian_query(frm);
		set_care_location_query(frm);
	},

	onload(frm) {
		set_attending_veterinarian_query(frm);
	},

	refresh(frm) {
		set_attending_veterinarian_query(frm);
		set_care_location_query(frm);
		set_hospitalisation_labels(frm);
		set_discharge_fields_visibility(frm);
		set_location_help(frm);
		set_activity_help(frm);
		add_hospitalisation_action_buttons(frm);
		add_clinical_activity_action_buttons(frm);
		add_stock_action_buttons(frm);
		add_care_location_action_buttons(frm);
		add_charge_sheet_action_buttons(frm);
	},
	status(frm) {
		set_discharge_fields_visibility(frm);
	},

	patient(frm) {
		void autofill_hospitalisation_patient_details(frm);
	},

	admission_datetime(frm) {
		update_hospitalisation_title_preview(frm);
	},

	attending_veterinarian(frm) {
		fetch_hospitalisation_veterinarian_title(frm);
	},

	admitted_by(frm) {
		fetch_hospitalisation_veterinarian_title(frm);
	},

	linked_consultation(frm) {
		autofill_hospitalisation_context_from_consultation(frm);
	},
});

function set_discharge_fields_visibility(frm) {
	const show_discharge_fields = ["Ready for Discharge", "Discharged"].includes(frm.doc.status);
	frm.toggle_display(["discharged_by", "discharge_datetime", "discharge_summary"], show_discharge_fields);
}


function set_hospitalisation_labels(frm) {
	frm.set_df_property("customer", "label", __("Pet Owner"));
}

function autofill_hospitalisation_patient_details(frm) {
	if (!frm.doc.patient) {
		return;
	}
	return frappe.db
		.get_value("Veterinary Patient", frm.doc.patient, [
			"patient_name",
			"primary_owner",
			"default_branch",
			"species",
			"breed",
			"sex",
			"approximate_age",
			"date_of_birth",
		])
		.then((result) => {
			const patient = result?.message || {};
			frm._hospitalisation_patient_title = patient.patient_name || frm.doc.patient;
			set_form_value_if_field_exists(frm, "customer", patient.primary_owner);
			set_form_value_if_field_exists(frm, "pet_owner", patient.primary_owner);
			set_form_value_if_field_exists(frm, "patient_name", patient.patient_name);
			set_form_value_if_field_exists(frm, "species", patient.species);
			set_form_value_if_field_exists(frm, "breed", patient.breed);
			set_form_value_if_field_exists(frm, "sex", patient.sex);
			set_form_value_if_field_exists(frm, "age", patient.approximate_age);
			set_form_value_if_field_exists(frm, "approximate_age", patient.approximate_age);
			set_form_value_if_field_exists(frm, "date_of_birth", patient.date_of_birth);
			if (!frm.doc.service_branch) {
				set_form_value_if_field_exists(frm, "service_branch", patient.default_branch);
			}
			refresh_hospitalisation_context_fields(frm);
			update_hospitalisation_title_preview(frm);
		});
}

function autofill_hospitalisation_context_from_consultation(frm) {
	if (!frm.doc.linked_consultation) {
		return;
	}
	frappe.db
		.get_value("Veterinary Consultation", frm.doc.linked_consultation, [
			"patient",
			"primary_owner",
			"service_branch",
			"company",
			"consulting_practitioner",
		])
		.then((result) => {
			const consultation = result?.message || {};
			set_form_value_if_field_exists(frm, "patient", consultation.patient);
			set_form_value_if_field_exists(frm, "customer", consultation.primary_owner);
			set_form_value_if_field_exists(frm, "pet_owner", consultation.primary_owner);
			set_form_value_if_field_exists(frm, "service_branch", consultation.service_branch);
			set_form_value_if_field_exists(frm, "company", consultation.company);
			set_form_value_if_field_exists(frm, "attending_veterinarian", consultation.consulting_practitioner);
			if (consultation.patient) {
				autofill_hospitalisation_patient_details(frm);
			}
			fetch_hospitalisation_veterinarian_title(frm);
		});
}

function set_attending_veterinarian_query(frm) {
	frm.set_query("attending_veterinarian", () => ({
		query: "vetedge.services.permissions.get_veterinary_doctor_users",
	}));
}


function set_care_location_query(frm) {
	frm.set_query("care_location", () => ({
		filters: {
			enabled: 1,
			branch: frm.doc.service_branch || undefined,
			status: ["in", ["Available", "Occupied"]],
		},
	}));
}

function has_form_field(frm, fieldname) {
	return Boolean(frm.fields_dict[fieldname] || frappe.meta.has_field(frm.doctype, fieldname));
}

function set_form_value_if_field_exists(frm, fieldname, value) {
	if (value !== undefined && value !== null && value !== "" && has_form_field(frm, fieldname) && frm.doc[fieldname] !== value) {
		frm.set_value(fieldname, value);
	}
}

function refresh_hospitalisation_context_fields(frm) {
	["customer", "pet_owner", "patient_name", "species", "breed", "sex", "age", "approximate_age", "date_of_birth", "owner_contact", "service_branch"].forEach((fieldname) => {
		if (has_form_field(frm, fieldname)) {
			frm.refresh_field(fieldname);
		}
	});
}

function fetch_hospitalisation_veterinarian_title(frm) {
	const user = frm.doc.attending_veterinarian || frm.doc.admitted_by;
	if (!user) {
		frm._hospitalisation_veterinarian_title = null;
		update_hospitalisation_title_preview(frm);
		return;
	}
	frappe.db.get_value("User", user, "full_name").then((result) => {
		frm._hospitalisation_veterinarian_title = result?.message?.full_name || user;
		update_hospitalisation_title_preview(frm);
	});
}

function update_hospitalisation_title_preview(frm) {
	if (!frm.fields_dict.hospitalisation_title) {
		return;
	}
	const patientTitle = frm._hospitalisation_patient_title || frm.doc.patient_name || frm.doc.patient;
	const parts = [patientTitle || __("Hospitalisation")];
	const admissionDate = get_hospitalisation_date_title(frm.doc.admission_datetime);
	const veterinarianTitle = frm._hospitalisation_veterinarian_title || frm.doc.attending_veterinarian || frm.doc.admitted_by;
	if (admissionDate) {
		parts.push(admissionDate);
	}
	if (veterinarianTitle) {
		parts.push(veterinarianTitle);
	}
	if (patientTitle) {
		parts.push(__("Hospitalisation"));
	}
	set_form_value_if_field_exists(frm, "hospitalisation_title", parts.join(" - "));
}

function get_hospitalisation_date_title(value) {
	if (!value) {
		return null;
	}
	const dateValue = String(value).split(/[ T]/)[0];
	return frappe.datetime.str_to_user(dateValue);
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
		["Add Medication", () => open_medication_multi_row_dialog(frm)],
		["Add Fluid Therapy", () => open_activity_dialog(frm, { activity_type: "Fluid Therapy", title: "Add Fluid Therapy" })],
		["Add Feeding", () => open_activity_dialog(frm, { activity_type: "Feeding", title: "Add Feeding" })],
		["Add Nursing Note", () => open_activity_dialog(frm, { activity_type: "Nursing Note", title: "Add Nursing Note" })],
		["Add Wound Care", () => open_activity_dialog(frm, { activity_type: "Wound Care", title: "Add Wound Care" })],
		["Add Procedure", () => open_billable_activity_dialog(frm, { activity_type: "Procedure", title: "Add Procedure" })],
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
				save_and_reload_hospitalisation_activity(frm, "Vitals added");
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
					save_and_reload_hospitalisation_activity(frm, "Vitals added");
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
			{ fieldtype: "Check", fieldname: "billable", label: __("Billable"), default: 1 },
			{ fieldtype: "Check", fieldname: "stock_affecting", label: __("Stock Affecting") },
			{ fieldtype: "Currency", fieldname: "rate", label: __("Rate if no item price exists") },
			{ fieldtype: "Small Text", fieldname: "notes", label: __("Notes") },
		],
		primary_action_label: __("Add"),
		primary_action(values) {
			if (!frm.doc.linked_consultation) {
				add_vaccination_activity_with_billing(frm, dialog, values);
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
					add_vaccination_activity_with_billing(frm, dialog, values, record.name);
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
					const selectedTests = state.selected.map((name) => tests.find((test) => test.name === name)).filter(Boolean);
					const missingRates = selectedTests.filter((test) => test.linked_item && !flt(test.default_rate));
					if (missingRates.length) {
						frappe.msgprint(__("Selected billable lab tests need a Default Rate before they can be added to hospitalisation charges."));
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
							add_lab_activities_with_billing(frm, values, selectedTests, order.name);
							dialog.hide();
							save_and_reload_hospitalisation_activity(frm, "Lab order added");
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
	save_and_reload_hospitalisation_activity(frm, `${values.activity_type || "Activity"} added`);
}


function save_and_reload_hospitalisation_activity(frm, message) {
    return frm.save().then(() => frm.reload_doc()).then(() => {
        if (message) {
            frappe.show_alert({ message: __(message), indicator: "green" });
        }
    });
}

function append_activity_row(frm, values) {
	const row = frm.add_child("activities");
	row.activity_reference = values.activity_reference || make_hospitalisation_activity_reference();
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
	return row;
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



function add_vaccination_activity_with_billing(frm, dialog, values, linkedDocument = null) {
	frappe.db.get_value("Veterinary Vaccine", values.vaccine, ["default_item"]).then((result) => {
		const item = result?.message?.default_item;
		const activityValues = {
			activity_type: "Vaccination",
			activity_datetime: values.administered_on,
			clinical_notes: format_vaccination_activity_notes(values),
			linked_doctype: linkedDocument ? "Veterinary Vaccination Record" : null,
			linked_document: linkedDocument,
			billable: values.billable && item,
			stock_affecting: values.stock_affecting,
			item,
			qty: 1,
		};
		if (!values.billable || !item) {
			append_activity_row(frm, activityValues);
			dialog.hide();
			save_and_reload_hospitalisation_activity(frm, "Vaccination added");
			return;
		}
		resolve_billing_rate(item, values.rate).then((billing) => {
			if (!billing.rate) {
				frappe.msgprint(__("Enter a rate before adding this billable vaccination."));
				return;
			}
			const activity = append_activity_row(frm, { ...activityValues, uom: billing.uom });
			append_charge_item_for_activity(frm, activity, {
				item,
				description: format_vaccination_activity_notes(values) || "Vaccination",
				qty: 1,
				uom: billing.uom,
				rate: billing.rate,
			});
			dialog.hide();
			save_and_reload_hospitalisation_activity(frm, "Vaccination added");
		});
	});
}

function add_lab_activities_with_billing(frm, values, tests, linkedDocument) {
	(tests || []).forEach((test) => {
		const item = test.linked_item;
		const activity = append_activity_row(frm, {
			activity_type: "Lab",
			clinical_notes: [test.test_name || test.name, values.sample_notes].filter(Boolean).join("\n"),
			linked_doctype: "Veterinary Lab Order",
			linked_document: linkedDocument,
			billable: Boolean(item),
			item,
			qty: 1,
		});
		if (item) {
			const rate = flt(test.default_rate);
			if (!rate) {
				frappe.show_alert({ message: __("Lab test has a billing item but no rate. Add a rate on the charge row before syncing."), indicator: "orange" });
			}
			append_charge_item_for_activity(frm, activity, {
				item,
				description: test.test_name || test.name,
				qty: 1,
				rate,
			});
		}
	});
}

function resolve_billing_rate(item, explicitRate) {
	if (flt(explicitRate)) {
		return Promise.resolve({ rate: flt(explicitRate) });
	}
	return frappe.db.get_value("Item", item, ["stock_uom", "standard_rate"]).then((result) => {
		const itemDoc = result?.message || {};
		return { rate: flt(itemDoc.standard_rate), uom: itemDoc.stock_uom };
	});
}

function open_billable_activity_dialog(frm, options = {}) {
	const activityType = options.activity_type || "Procedure";
	const dialog = new frappe.ui.Dialog({
		title: __(options.title || `Add ${activityType}`),
		fields: [
			{ fieldname: "clinical_notes", fieldtype: "Text Editor", label: __("Clinical Notes") },
			{ fieldname: "item", fieldtype: "Link", label: __("Billing Item"), options: "Item", reqd: 1 },
			{ fieldname: "qty", fieldtype: "Float", label: __("Qty"), default: 1 },
			{ fieldname: "uom", fieldtype: "Link", label: __("UOM"), options: "UOM" },
			{ fieldname: "rate", fieldtype: "Currency", label: __("Rate") },
			{ fieldname: "stock_affecting", fieldtype: "Check", label: __("Stock Affecting") },
		],
		primary_action_label: __("Add"),
		primary_action(values) {
			add_billable_activity_with_rate(frm, dialog, {
				...values,
				activity_type: activityType,
				billable: 1,
			});
		},
	});
	dialog.show();
}

function open_medication_multi_row_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Add Medication"),
		size: "extra-large",
		fields: [
			{
				fieldname: "medications",
				fieldtype: "Table",
				label: __("Medications"),
				cannot_add_rows: false,
				in_place_edit: true,
				data: [{}],
				fields: get_medication_dialog_table_fields(frm, () => dialog),
			},
		],
		primary_action_label: __("Add Medications"),
		primary_action() {
			const rows = get_medication_dialog_rows(dialog);
			if (!rows.length) {
				frappe.msgprint(__("Add at least one medication row."));
				return;
			}
			add_medication_rows(frm, dialog, rows);
		},
	});
	dialog.show();
}

function get_medication_dialog_table_fields(frm, get_dialog) {
	const refresh_grid = () => {
		const dialog = get_dialog();
		if (dialog?.fields_dict?.medications?.grid) {
			dialog.fields_dict.medications.grid.refresh();
		}
	};
	const update_amount = function () {
		this.doc.amount = (flt(this.doc.qty) || 0) * (flt(this.doc.rate) || 0);
		refresh_grid();
	};
	return [
		{ fieldname: "item", fieldtype: "Link", label: __("Medication Item"), options: "Item", in_list_view: 1, reqd: 1, columns: 2, onchange: function () { hydrate_medication_item_row(frm, get_dialog(), this.doc); } },
		{ fieldname: "item_name", fieldtype: "Data", label: __("Item Name"), read_only: 1, columns: 2 },
		{ fieldname: "qty", fieldtype: "Float", label: __("Qty"), default: 1, in_list_view: 1, columns: 1, onchange: update_amount },
		{ fieldname: "uom", fieldtype: "Link", label: __("UOM"), options: "UOM", in_list_view: 1, columns: 1 },
		{ fieldname: "dosage", fieldtype: "Data", label: __("Dosage"), columns: 1 },
		{ fieldname: "route", fieldtype: "Data", label: __("Route"), columns: 1 },
		{ fieldname: "frequency", fieldtype: "Data", label: __("Frequency"), columns: 1 },
		{ fieldname: "notes", fieldtype: "Small Text", label: __("Notes"), columns: 2 },
		{ fieldname: "billable", fieldtype: "Check", label: __("Billable"), in_list_view: 1, columns: 1 },
		{ fieldname: "stock_affecting", fieldtype: "Check", label: __("Stock"), in_list_view: 1, columns: 1 },
		{ fieldname: "rate", fieldtype: "Currency", label: __("Rate"), in_list_view: 1, columns: 1, onchange: update_amount },
		{ fieldname: "amount", fieldtype: "Currency", label: __("Amount"), read_only: 1, columns: 1 },
		{ fieldname: "pricing_source", fieldtype: "Data", label: __("Pricing Source"), read_only: 1, columns: 1 },
		{ fieldname: "missing_price", fieldtype: "Check", label: __("Missing Price"), hidden: 1 },
	];
}

function hydrate_medication_item_row(frm, dialog, row) {
	if (!row?.item) {
		return;
	}
	frappe.call({
		method: "vetedge.services.hospitalisation.get_hospitalisation_medication_item_context",
		args: { hospitalisation_name: frm.doc.name, item: row.item, uom: row.uom },
		callback(result) {
			const context = result.message || {};
			row.item_name = context.item_name || row.item;
			row.uom = row.uom || context.uom;
			row.stock_affecting = context.is_stock_item ? 1 : 0;
			if (flt(context.rate) > 0) {
				row.rate = flt(context.rate);
				row.billable = 1;
				row.pricing_source = context.pricing_source || __("Selling Price");
				row.missing_price = 0;
			} else {
				row.rate = row.rate || 0;
				row.billable = 0;
				row.pricing_source = "";
				row.missing_price = 1;
			}
			row.qty = flt(row.qty) || 1;
			row.amount = flt(row.qty) * flt(row.rate);
			dialog.fields_dict.medications.grid.refresh();
		},
	});
}

function get_medication_dialog_rows(dialog) {
	const rows = (dialog.get_value("medications") || []).filter((row) => row.item || row.dosage || row.notes);
	return rows.map((row) => ({
		item: row.item,
		item_name: row.item_name,
		qty: flt(row.qty) || 0,
		uom: row.uom,
		dosage: row.dosage,
		route: row.route,
		frequency: row.frequency,
		notes: row.notes,
		billable: row.billable ? 1 : 0,
		stock_affecting: row.stock_affecting ? 1 : 0,
		rate: flt(row.rate) || 0,
		amount: flt(row.amount) || ((flt(row.qty) || 0) * (flt(row.rate) || 0)),
		pricing_source: row.pricing_source,
		missing_price: row.missing_price ? 1 : 0,
	}));
}

function add_medication_rows(frm, dialog, rows) {
	for (const row of rows) {
		if (!row.item) {
			frappe.msgprint(__("Select an Item for each medication row."));
			return;
		}
		if (flt(row.qty) <= 0) {
			frappe.msgprint(__("Enter quantity greater than zero."));
			return;
		}
		if (row.billable && flt(row.rate) <= 0) {
			frappe.msgprint(__("Rate is required for billable medication where no selling price was found."));
			return;
		}
	}
	rows.forEach((row) => {
		const notes = [
			row.dosage && `${__("Dosage")}: ${row.dosage}`,
			row.route && `${__("Route")}: ${row.route}`,
			row.frequency && `${__("Frequency")}: ${row.frequency}`,
			row.notes,
		].filter(Boolean).join("\n");
		const activity = append_activity_row(frm, {
			activity_type: "Medication",
			clinical_notes: notes,
			billable: row.billable,
			stock_affecting: row.stock_affecting,
			item: row.item,
			qty: flt(row.qty),
			uom: row.uom,
		});
		if (row.billable) {
			append_charge_item_for_activity(frm, activity, {
				item: row.item,
				description: notes || row.item_name || "Medication",
				qty: flt(row.qty),
				uom: row.uom,
				rate: flt(row.rate),
				notes: row.pricing_source,
			});
		}
	});
	dialog.hide();
	save_and_reload_hospitalisation_activity(frm, "Medication added");
}

function add_billable_activity_with_rate(frm, dialog, values) {
	if (!values.item) {
		frappe.msgprint(__("Select a billing item."));
		return;
	}
	if (!flt(values.rate)) {
		frappe.msgprint(__("Enter a rate before adding this billable activity."));
		return;
	}
	const activity = append_activity_row(frm, values);
	append_charge_item_for_activity(frm, activity, values);
	dialog.hide();
	save_and_reload_hospitalisation_activity(frm, `${values.activity_type || "Activity"} added`);
}

function append_charge_item_for_activity(frm, activity, values) {
	const row = frm.add_child("charge_items");
	const qty = flt(values.qty) || 1;
	const rate = flt(values.rate);
	const sourceActivity = activity.activity_reference || activity.name || make_hospitalisation_activity_reference();
	activity.activity_reference = sourceActivity;
	row.source_activity = sourceActivity;
	row.activity_type = activity.activity_type;
	row.item = values.item;
	row.description = values.description || values.clinical_notes || activity.clinical_notes || activity.activity_type;
	row.qty = qty;
	row.uom = values.uom;
	row.rate = rate;
	row.amount = qty * rate;
	row.billing_status = "Pending Invoice";
	row.source_hash = `${frm.doc.name}:${sourceActivity}:${values.item}`;
	row.pricing_source = values.pricing_source;
	row.notes = values.notes || values.clinical_notes;
	frm.refresh_field("charge_items");
	frm.dirty();
}

function make_hospitalisation_activity_reference() {
	if (frappe.utils?.get_random) {
		return frappe.utils.get_random(12);
	}
	return `${frappe.datetime.now_datetime()}-${Math.random().toString(36).slice(2, 10)}`;
}

function preview_stock_usage(frm) {
	frappe.call({
		method: "vetedge.services.hospitalisation.get_hospitalisation_stock_posting_preview",
		args: { hospitalisation_name: frm.doc.name },
		freeze: true,
		freeze_message: __("Checking stock usage..."),
		callback(result) {
			show_stock_usage_preview(frm, result.message || {});
		},
	});
}

function show_stock_usage_preview(frm, summary) {
	const readyRows = summary.items || [];
	const blockedRows = summary.blocked || [];
	const skippedRows = summary.skipped || [];
	const message = [
		`${__("Ready to Post")}: ${summary.to_post_count || 0}`,
		`${__("Skipped")}: ${summary.skipped_count || 0}`,
		`${__("Blocked")}: ${summary.blocked_count || 0}`,
		readyRows.length ? `<br><b>${__("Items")}</b><br>${readyRows.map(format_stock_preview_row).join("<br>")}` : null,
		blockedRows.length ? `<br><b>${__("Blocked")}</b><br>${blockedRows.map(format_stock_preview_row).join("<br>")}` : null,
		skippedRows.length ? `<br><b>${__("Skipped")}</b><br>${skippedRows.map(format_stock_preview_row).join("<br>")}` : null,
	].filter(Boolean).join("<br>");
	const dialog = new frappe.ui.Dialog({
		title: __("Post Stock Usage"),
		fields: [{ fieldname: "preview", fieldtype: "HTML", options: message }],
		primary_action_label: __("Confirm Post"),
		primary_action() {
			if (!readyRows.length) {
				frappe.msgprint(__("There are no stock rows ready to post."));
				return;
			}
			dialog.hide();
			post_stock_usage(frm);
		},
	});
	dialog.show();
}

function format_stock_preview_row(row) {
	return frappe.utils.escape_html([row.activity_type, row.item, row.qty, row.uom, row.warehouse, row.message].filter(Boolean).join(" | "));
}

function post_stock_usage(frm) {
	frappe.call({
		method: "vetedge.services.hospitalisation.post_hospitalisation_activity_stock",
		args: { hospitalisation_name: frm.doc.name },
		freeze: true,
		freeze_message: __("Posting stock usage..."),
		callback(result) {
			const summary = result.message || {};
			frm.reload_doc().then(() => {
				frappe.msgprint({
					title: __("Stock Usage"),
					message: [
						`${__("Posted")}: ${summary.posted_count || 0}`,
						`${__("Skipped")}: ${summary.skipped_count || 0}`,
						`${__("Blocked")}: ${summary.blocked_count || 0}`,
					].join("<br>"),
					indicator: summary.blocked_count ? "orange" : "green",
				});
			});
		},
	});
}

function add_stock_action_buttons(frm) {
	if (frm.is_new() || ["Cancelled", "Discharged"].includes(frm.doc.status)) {
		return;
	}

	frm.add_custom_button(__("Post Stock Usage"), () => {
		preview_stock_usage(frm);
	}, __("Stock"));
}

function get_hospitalisation_date(value) {
	return value ? String(value).slice(0, 10) : null;
}

function open_generate_daily_charges_dialog(frm) {
	const defaultFromDate = get_hospitalisation_date(frm.doc.admission_datetime) || frappe.datetime.now_date();
	const defaultToDate = get_hospitalisation_date(frm.doc.discharge_datetime) || frappe.datetime.now_date();
	const careLevelOptions = ["Standard", "Observation", "Intensive Care", "ICU", "Isolation", "Recovery"].join("\n");
	const dialog = new frappe.ui.Dialog({
		title: __("Generate Daily Charges"),
		fields: [
			{ fieldname: "from_date", fieldtype: "Date", label: __("From Date"), default: defaultFromDate, reqd: 1 },
			{ fieldname: "to_date", fieldtype: "Date", label: __("To Date"), default: defaultToDate, reqd: 1 },
			{ fieldname: "care_level", fieldtype: "Select", label: __("Care Level"), options: careLevelOptions, default: frm.doc.care_level || "Standard", reqd: 1 },
		],
		primary_action_label: __("Generate"),
		primary_action(values) {
			frappe.call({
				method: "vetedge.services.hospitalisation.generate_hospitalisation_daily_charges",
				args: { hospitalisation_name: frm.doc.name, from_date: values.from_date, to_date: values.to_date, care_level: values.care_level },
				freeze: true,
				callback(result) {
					const summary = result.message || {};
					dialog.hide();
					frm.reload_doc().then(() => {
						frappe.msgprint({
							title: __("Daily Charges"),
							message: [
								summary.message,
								`${__("Created")}: ${summary.created || 0}`,
								`${__("Updated")}: ${summary.updated || 0}`,
								`${__("Existing")}: ${summary.skipped_existing || 0}`,
								`${__("Missing Price")}: ${summary.missing_price || 0}`,
								`${__("Total")}: ${format_currency(summary.total_amount || 0)}`,
							].filter(Boolean).join("<br>"),
						});
					});
				},
			});
		},
	});
	dialog.show();
}


function add_care_location_action_buttons(frm) {
	if (frm.is_new() || frm.doc.status === "Cancelled") {
		return;
	}

	frm.add_custom_button(__("View Available Locations"), () => {
		show_available_care_locations(frm);
	}, __("Care Location"));

	if (frm.doc.status !== "Discharged") {
		frm.add_custom_button(__("Assign Care Location"), () => {
			open_assign_care_location_dialog(frm);
		}, __("Care Location"));
	}

	if (frm.doc.care_location) {
		frm.add_custom_button(__("Release Care Location"), () => {
			open_release_care_location_dialog(frm);
		}, __("Care Location"));
	}
}

function open_assign_care_location_dialog(frm) {
	const locationTypeOptions = ["", "Ward", "Kennel", "Cage", "ICU", "Isolation", "Recovery", "General"].join("\n");
	const dialog = new frappe.ui.Dialog({
		title: __("Assign Care Location"),
		fields: [
			{ fieldname: "location_type", fieldtype: "Select", label: __("Location Type"), options: locationTypeOptions, default: frm.doc.care_location_type === "Not Assigned" ? "" : frm.doc.care_location_type },
			{ fieldname: "care_location", fieldtype: "Link", label: __("Care Location"), options: "Veterinary Care Location", reqd: 1 },
			{ fieldname: "notes", fieldtype: "Small Text", label: __("Notes") },
		],
		primary_action_label: __("Assign"),
		primary_action(values) {
			frappe.call({
				method: "vetedge.services.hospitalisation.assign_hospitalisation_care_location",
				args: { hospitalisation_name: frm.doc.name, care_location: values.care_location, notes: values.notes },
				freeze: true,
				callback(result) {
					const response = result.message || {};
					dialog.hide();
					frm.reload_doc().then(() => frappe.msgprint(response.message || __("Care location assigned.")));
				},
			});
		},
	});
	dialog.fields_dict.care_location.get_query = () => ({
		filters: {
			enabled: 1,
			branch: frm.doc.service_branch || undefined,
			location_type: dialog.get_value("location_type") || undefined,
			status: ["in", ["Available", "Occupied"]],
		},
	});
	dialog.show();
}

function open_release_care_location_dialog(frm) {
	frappe.prompt(
		[{ fieldname: "notes", fieldtype: "Small Text", label: __("Release Notes") }],
		(values) => {
			frappe.confirm(__("Release the assigned care location?"), () => {
				frappe.call({
					method: "vetedge.services.hospitalisation.release_hospitalisation_care_location",
					args: { hospitalisation_name: frm.doc.name, notes: values.notes },
					freeze: true,
					callback(result) {
						const response = result.message || {};
						frm.reload_doc().then(() => frappe.msgprint(response.message || __("Care location released.")));
					},
				});
			});
		},
		__("Release Care Location"),
		__("Continue")
	);
}

function show_available_care_locations(frm) {
	frappe.call({
		method: "vetedge.services.hospitalisation.get_available_care_locations",
		args: { branch: frm.doc.service_branch, location_type: frm.doc.care_location_type === "Not Assigned" ? null : frm.doc.care_location_type, care_level: frm.doc.care_level },
		freeze: true,
		callback(result) {
			const rows = result.message || [];
			const message = rows.length
				? rows.map((row) => `${frappe.utils.escape_html(row.location_name || row.name)} - ${frappe.utils.escape_html(row.location_type || "-")} - ${__("Slots")}: ${row.available_slots}`).join("<br>")
				: __("No available care locations found for this filter.");
			frappe.msgprint({ title: __("Available Care Locations"), message });
		},
	});
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
						`${__("Total Hospitalisation Charges")}: ${format_currency(summary.total_charge_amount || 0)}`,
						`${__("Pending Charges")}: ${format_currency(summary.pending_charge_amount || summary.total_pending || 0)}`,
						`${__("Invoiced Charges")}: ${format_currency(summary.invoiced_charge_amount || summary.total_invoiced || 0)}`,
						`${__("Cancelled")}: ${format_currency(summary.cancelled_charge_amount || summary.total_cancelled || 0)}`,
						`${__("Missing Price")}: ${summary.missing_price_count || 0}`,
						`${__("Not Billable Activities")}: ${summary.not_billable_count || 0}`,
						`${__("Linked Invoice")}: ${summary.linked_invoice || "-"}`,
					].join("<br>"),
				});
			},
		});
	}, __("Billing"));

	if (["Admitted", "Under Care", "Ready for Discharge", "Discharged"].includes(frm.doc.status)) {
		frm.add_custom_button(__("Generate Daily Charges"), () => {
			open_generate_daily_charges_dialog(frm);
		}, __("Billing"));
	}

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
					const after_reload = () => {
						if (gate.message) {
							frappe.msgprint({
								message: gate.message,
								indicator: gate.can_proceed ? "green" : "red",
							});
						}
						if (!gate.can_proceed && gate.open_billing_modal && window.vetedgeBillingModal?.open) {
							window.vetedgeBillingModal.open(frm);
						}
					};
					if (gate.reload_required || gate.hospitalisation_mutated) {
						frm.reload_doc().then(after_reload);
					} else {
						after_reload();
					}
				},
				error(result) {
					const message = result.message || result.exc || __("Hospitalisation admission could not be completed.");
					frm.reload_doc().then(() => frappe.msgprint({ message, indicator: "red" }));
				},
			});
		}, __("Clinical"));
	}

	if (["Admitted", "Under Care", "Ready for Discharge"].includes(frm.doc.status)) {
		frm.add_custom_button(__("Check Discharge Readiness"), () => {
			check_discharge_readiness(frm);
		}, __("Clinical"));

		frm.add_custom_button(__("Discharge"), () => {
			open_discharge_dialog(frm);
		}, __("Clinical"));
	}
}

function check_discharge_readiness(frm) {
	frappe.call({
		method: "vetedge.services.hospitalisation.get_hospitalisation_discharge_readiness",
		args: { hospitalisation_name: frm.doc.name },
		freeze: true,
		callback(result) {
			show_discharge_readiness_dialog(frm, result.message || {});
		},
	});
}

function show_discharge_readiness_dialog(frm, readiness) {
	const messages = readiness.messages || readiness.warnings || [];
	const actions = readiness.recommended_actions || [];
	frappe.msgprint({
		title: __("Discharge Readiness"),
		message: [
			`${__("Can Discharge")}: ${readiness.can_discharge ? __("Yes") : __("No")}`,
			`${__("Pending Billable Activities")}: ${(readiness.pending_billable_activities || []).length}`,
			`${__("Pending Charge Items")}: ${(readiness.pending_charge_items || []).length}`,
			`${__("Pending Stock Activities")}: ${(readiness.pending_stock_activities || []).length}`,
			`${__("Billing Status")}: ${readiness.discharge_billing_status || "-"}`,
			messages.length ? `<br><b>${__("Messages")}</b><br>${messages.map(frappe.utils.escape_html).join("<br>")}` : null,
			actions.length ? `<br><b>${__("Recommended Actions")}</b><br>${actions.map(frappe.utils.escape_html).join("<br>")}` : null,
		].filter(Boolean).join("<br>"),
		indicator: readiness.can_discharge ? "green" : "orange",
	});
	if (!readiness.can_discharge && actions.includes("Open Billing & Payment") && window.vetedgeBillingModal?.open) {
		window.vetedgeBillingModal.open(frm);
	}
}

function open_discharge_dialog(frm) {
	frappe.prompt(
		[
			{ fieldname: "condition_at_discharge", fieldtype: "Select", label: __("Condition at Discharge"), options: "\nRecovered\nStable\nImproved\nReferred\nTransferred\nDied\nEuthanised\nDischarged Against Medical Advice" },
			{ fieldname: "discharge_summary", fieldtype: "Text Editor", label: __("Discharge Summary"), reqd: 1, default: frm.doc.discharge_summary },
			{ fieldname: "discharge_instructions", fieldtype: "Text Editor", label: __("Discharge Instructions"), default: frm.doc.discharge_instructions },
			{ fieldname: "follow_up_date", fieldtype: "Date", label: __("Follow Up Date"), default: frm.doc.follow_up_date },
			{ fieldname: "follow_up_notes", fieldtype: "Text Editor", label: __("Follow Up Notes"), default: frm.doc.follow_up_notes },
		],
		(values) => {
			frappe.call({
				method: "vetedge.services.hospitalisation.discharge_hospitalisation",
				args: {
					hospitalisation_name: frm.doc.name,
					discharge_details: values,
				},
				freeze: true,
				callback(result) {
					const response = result.message || {};
					frappe.show_alert({ message: __("Hospitalisation discharged"), indicator: "green" });
					if (response.readiness?.messages?.length) {
						frappe.msgprint(response.readiness.messages.join("<br>"));
					}
					frm.reload_doc();
				},
				error(result) {
					const message = result.message || result.exc || __("Hospitalisation is not ready for discharge.");
					frm.reload_doc().then(() => {
						frappe.msgprint({ message, indicator: "red" });
						if (window.vetedgeBillingModal?.open) {
							window.vetedgeBillingModal.open(frm);
						}
					});
				},
			});
		},
		__("Discharge Hospitalisation"),
		__("Discharge")
	);
}
