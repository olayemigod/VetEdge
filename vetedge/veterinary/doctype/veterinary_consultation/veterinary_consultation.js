frappe.ui.form.on("Veterinary Consultation", {
	setup(frm) {
		frm.set_query("patient", () => ({
			filters: {
				status: ["!=", "Deceased"],
			},
		}));

		frm.set_query("symptom", "symptoms", () => ({
			filters: {
				disabled: 0,
			},
		}));

		frm.set_query("diagnosis", "diagnoses", () => ({
			filters: {
				disabled: 0,
			},
		}));

		frm.set_query("item", "planned_treatments", () => ({
			filters: {
				disabled: 0,
			},
		}));
	},

	refresh(frm) {
		if (!frm.is_new() && frm.doc.patient && frm.doc.service_branch) {
			frm.add_custom_button(__("New Vitals"), () => {
				show_vitals_entry_dialog(frm);
			});

			frm.add_custom_button(__("Latest Vitals"), () => {
				show_latest_vitals_dialog(frm);
			});
		}
	},

	patient(frm) {
		if (!frm.doc.patient) {
			return;
		}

		frappe.db
			.get_value("Veterinary Patient", frm.doc.patient, ["primary_owner", "default_branch"])
			.then((result) => {
				const patient = result?.message || {};
				if (patient.primary_owner) {
					frm.set_value("primary_owner", patient.primary_owner);
				}
				if (!frm.doc.service_branch && patient.default_branch) {
					frm.set_value("service_branch", patient.default_branch);
				}
			});
	},

	consulting_practitioner(frm) {
		if (!frm.doc.consulting_practitioner) {
			frm.set_value("consulting_practitioner_name", "");
			return;
		}

		frappe.db
			.get_value("User", frm.doc.consulting_practitioner, "full_name")
			.then((result) => {
				const full_name = result?.message?.full_name;
				frm.set_value(
					"consulting_practitioner_name",
					full_name || frm.doc.consulting_practitioner
				);
			});
	},
});

function show_vitals_entry_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("New Vitals"),
		fields: [
			{
				fieldname: "recorded_on",
				fieldtype: "Datetime",
				label: __("Recorded On"),
				default: frappe.datetime.now_datetime(),
				reqd: 1,
			},
			{ fieldname: "vitals_section", fieldtype: "Section Break", label: __("Vitals") },
			{ fieldname: "temperature", fieldtype: "Float", label: __("Temperature") },
			{ fieldname: "weight", fieldtype: "Float", label: __("Weight") },
			{ fieldname: "heart_rate", fieldtype: "Int", label: __("Heart Rate") },
			{ fieldname: "respiratory_rate", fieldtype: "Int", label: __("Respiratory Rate") },
			{ fieldname: "column_break_vitals", fieldtype: "Column Break" },
			{
				fieldname: "body_condition_score",
				fieldtype: "Select",
				label: __("Body Condition Score"),
				options: "\n1\n2\n3\n4\n5\n6\n7\n8\n9",
			},
			{
				fieldname: "hydration_status",
				fieldtype: "Select",
				label: __("Hydration Status"),
				options: "\nNormal\nMild Dehydration\nModerate Dehydration\nSevere Dehydration",
			},
			{
				fieldname: "mucous_membrane",
				fieldtype: "Select",
				label: __("Mucous Membrane"),
				options: "\nPink\nPale\nIcteric\nCyanotic\nCongested",
			},
			{
				fieldname: "capillary_refill_time",
				fieldtype: "Data",
				label: __("Capillary Refill Time"),
			},
			{
				fieldname: "pain_score",
				fieldtype: "Select",
				label: __("Pain Score"),
				options: "\n0\n1\n2\n3\n4\n5\n6\n7\n8\n9\n10",
			},
			{
				fieldname: "appetite_status",
				fieldtype: "Select",
				label: __("Appetite Status"),
				options: "\nNormal\nReduced\nAbsent\nIncreased\nUnknown",
			},
			{ fieldname: "notes", fieldtype: "Small Text", label: __("Notes") },
		],
		primary_action_label: __("Save Vitals"),
		primary_action(values) {
			frappe.call({
				method: "vetedge.services.vitals.create_vitals_from_consultation",
				args: {
					consultation: frm.doc.name,
					values,
				},
				freeze: true,
				freeze_message: __("Saving vitals..."),
				callback(result) {
					if (result.message) {
						dialog.hide();
						frappe.show_alert({
							message: __("Vitals saved"),
							indicator: "green",
						});
					}
				},
			});
		},
	});

	dialog.show();
}

function show_latest_vitals_dialog(frm) {
	frappe.call({
		method: "vetedge.services.vitals.get_latest_vitals_for_consultation",
		args: {
			consultation: frm.doc.name,
		},
		callback(result) {
			const vitals = result.message;
			if (!vitals?.name) {
				frappe.msgprint(__("No vitals found for this consultation or patient."));
				return;
			}

			const dialog = new frappe.ui.Dialog({
				title: __("Latest Vitals"),
				fields: [
					{
						fieldname: "recorded_on",
						fieldtype: "Datetime",
						label: __("Recorded On"),
						read_only: 1,
					},
					{
						fieldname: "service_branch",
						fieldtype: "Link",
						label: __("Service Branch"),
						options: "Branch",
						read_only: 1,
					},
					{ fieldname: "vitals_section", fieldtype: "Section Break", label: __("Vitals") },
					{
						fieldname: "temperature",
						fieldtype: "Float",
						label: __("Temperature"),
						read_only: 1,
					},
					{ fieldname: "weight", fieldtype: "Float", label: __("Weight"), read_only: 1 },
					{
						fieldname: "heart_rate",
						fieldtype: "Int",
						label: __("Heart Rate"),
						read_only: 1,
					},
					{
						fieldname: "respiratory_rate",
						fieldtype: "Int",
						label: __("Respiratory Rate"),
						read_only: 1,
					},
					{ fieldname: "column_break_vitals", fieldtype: "Column Break" },
					{
						fieldname: "body_condition_score",
						fieldtype: "Data",
						label: __("Body Condition Score"),
						read_only: 1,
					},
					{
						fieldname: "hydration_status",
						fieldtype: "Data",
						label: __("Hydration Status"),
						read_only: 1,
					},
					{
						fieldname: "mucous_membrane",
						fieldtype: "Data",
						label: __("Mucous Membrane"),
						read_only: 1,
					},
					{
						fieldname: "capillary_refill_time",
						fieldtype: "Data",
						label: __("Capillary Refill Time"),
						read_only: 1,
					},
					{
						fieldname: "pain_score",
						fieldtype: "Data",
						label: __("Pain Score"),
						read_only: 1,
					},
					{
						fieldname: "appetite_status",
						fieldtype: "Data",
						label: __("Appetite Status"),
						read_only: 1,
					},
					{ fieldname: "notes", fieldtype: "Small Text", label: __("Notes"), read_only: 1 },
				],
			});

			dialog.set_values(vitals);
			dialog.show();
		},
	});
}
