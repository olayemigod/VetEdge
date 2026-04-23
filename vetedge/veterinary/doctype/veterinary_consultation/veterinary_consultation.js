frappe.ui.form.on("Veterinary Consultation", {
	setup(frm) {
		frm.set_query("patient", () => ({
			filters: {
				status: ["!=", "Deceased"],
			},
		}));

		frm.set_query("linked_appointment", () => ({
			query: "vetedge.services.consultation_flow.get_pending_appointments_for_patient",
			filters: {
				patient: frm.doc.patient,
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
		configure_dispensary_grid(frm);
		sync_dispensary_preview(frm);

		if (!frm.is_new() && frm.doc.patient && frm.doc.service_branch) {
			add_appointment_link_actions(frm);
			add_status_actions(frm);
			add_dispensary_actions(frm);

			frm.add_custom_button(__("New Vitals"), () => {
				show_vitals_entry_dialog(frm);
			}, __("Clinical"));

			frm.add_custom_button(__("Latest Vitals"), () => {
				show_latest_vitals_dialog(frm);
			}, __("Clinical"));

			frm.add_custom_button(__("Create Follow-up Appointment"), () => {
				show_follow_up_appointment_dialog(frm);
			}, __("Clinical"));

			add_billing_actions(frm);
		}
	},

	patient(frm) {
		if (!frm.doc.patient) {
			frm.set_value("linked_appointment", "");
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

	linked_appointment(frm) {
		if (!frm.doc.linked_appointment) {
			return;
		}

		frappe.db
			.get_value("Veterinary Appointment", frm.doc.linked_appointment, [
				"patient",
				"branch",
				"practitioner",
				"notes",
			])
			.then((result) => {
				const appointment = result?.message || {};
				if (appointment.patient && frm.doc.patient && appointment.patient !== frm.doc.patient) {
					frm.set_value("linked_appointment", "");
					frappe.msgprint(__("Selected appointment does not belong to this patient."));
					return;
				}
				if (appointment.patient && !frm.doc.patient) {
					frm.set_value("patient", appointment.patient);
				}
				if (appointment.branch && !frm.doc.service_branch) {
					frm.set_value("service_branch", appointment.branch);
				}
				if (appointment.practitioner && !frm.doc.consulting_practitioner) {
					frm.set_value("consulting_practitioner", appointment.practitioner);
				}
				if (appointment.notes && !frm.doc.presenting_complaint) {
					frm.set_value("presenting_complaint", appointment.notes);
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

	planned_treatments_add(frm) {
		sync_dispensary_preview(frm, true);
	},

	planned_treatments_remove(frm) {
		sync_dispensary_preview(frm, true);
	},
});

function add_appointment_link_actions(frm) {
	if (frm.doc.linked_appointment) {
		frm.add_custom_button(__("Open Service Appointment"), () => {
			frappe.set_route("Form", "Veterinary Appointment", frm.doc.linked_appointment);
		}, __("Appointment"));
	}

	if (frm.doc.follow_up_appointment) {
		frm.add_custom_button(__("Open Follow-up Appointment"), () => {
			frappe.set_route("Form", "Veterinary Appointment", frm.doc.follow_up_appointment);
		}, __("Appointment"));
	}
}

frappe.ui.form.on("Planned Treatment Item", {
	item(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item) {
			return;
		}

		frappe.db.get_value("Item", row.item, ["stock_uom", "standard_rate"]).then((result) => {
			const item = result?.message || {};
			if (!row.uom && item.stock_uom) {
				frappe.model.set_value(cdt, cdn, "uom", item.stock_uom);
			}
			if (!flt(row.rate) && flt(item.standard_rate)) {
				frappe.model.set_value(cdt, cdn, "rate", flt(item.standard_rate));
			}
			update_planned_treatment_amount(cdt, cdn);
		});

		frappe.call({
			method: "vetedge.services.treatment_items.get_treatment_item_defaults_for_consultation",
			args: {
				item_code: row.item,
			},
			callback(result) {
				const defaults = result.message || {};
				if (!row.service_type && defaults.service_type) {
					frappe.model.set_value(cdt, cdn, "service_type", defaults.service_type);
				}
				if (!row.treatment_type && defaults.treatment_type) {
					frappe.model.set_value(cdt, cdn, "treatment_type", defaults.treatment_type);
				}
				sync_dispensary_preview(frm, true);
			},
		});
	},
	qty(frm, cdt, cdn) {
		update_planned_treatment_amount(cdt, cdn);
		sync_dispensary_preview(frm, true);
	},
	rate(frm, cdt, cdn) {
		update_planned_treatment_amount(cdt, cdn);
	},
	treatment_type(frm) {
		sync_dispensary_preview(frm, true);
	},
	service_type(frm) {
		sync_dispensary_preview(frm, true);
	},
});

function update_planned_treatment_amount(cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "amount", flt(row.qty) * flt(row.rate));
}

function configure_dispensary_grid(frm) {
	const grid = frm.get_field("dispensed_treatments")?.grid;
	if (!grid) {
		return;
	}

	frm.set_query("selected_batch", "dispensed_treatments", (_doc, _cdt, cdn) => {
		const row = locals["Dispensed Treatment Item"]?.[cdn];
		return {
			filters: {
				item: row?.item,
				disabled: 0,
			},
		};
	});

	grid.cannot_add_rows = true;
	grid.only_sortable();
	frm.set_df_property(
		"dispensed_treatments",
		"read_only",
		!["Pending Dispensary", "Not Required"].includes(frm.doc.dispensary_status)
	);
	frm.refresh_field("dispensed_treatments");
}

function sync_dispensary_preview(frm, force = false) {
	if (frm.is_new()) {
		return;
	}

	const currentRows = frm.doc.dispensed_treatments || [];
	if (frm.doc.dispensary_status !== "Pending Dispensary") {
		if (frm.doc.dispensary_status === "Not Required" && currentRows.length && !frm.doc.dispensary_stock_entry) {
			frm.clear_table("dispensed_treatments");
			frm.refresh_field("dispensed_treatments");
		}
		configure_dispensary_grid(frm);
		return;
	}

	if (!force && currentRows.length) {
		configure_dispensary_grid(frm);
		return;
	}

	frappe.call({
		method: "vetedge.services.dispensary.get_dispensed_item_preview",
		args: {
			consultation: frm.doc.name,
		},
		callback(result) {
			const items = result.message?.items || [];
			const existingRowsByPlan = Object.fromEntries(
				(currentRows || []).map((row) => [row.planned_treatment_row, row])
			);
			frm.clear_table("dispensed_treatments");
			items.forEach((item) => {
				const row = frm.add_child("dispensed_treatments");
				Object.entries(item).forEach(([key, value]) => {
					row[key] = value;
				});
				const existing = existingRowsByPlan[item.planned_treatment_row];
				if (existing) {
					row.dispensed_qty = existing.dispensed_qty || row.dispensed_qty;
					row.notes = existing.notes || row.notes;
					row.selected_batch = existing.selected_batch || row.selected_batch;
				}
			});
			frm.refresh_field("dispensed_treatments");
			configure_dispensary_grid(frm);
		},
	});
}

function add_billing_actions(frm) {
	if (frm.doc.linked_invoice) {
		frm.add_custom_button(__("Open Invoice"), () => {
			window.open(
				frappe.urllib.get_full_url(`/app/sales-invoice/${encodeURIComponent(frm.doc.linked_invoice)}`),
				"_blank"
			);
		}, __("Billing"));
		return;
	}

	if (!["Completed", "Cancelled"].includes(frm.doc.status)) {
		frm.add_custom_button(__("Create Invoice"), () => {
			create_consultation_invoice(frm);
		}, __("Billing"));
	}
}

function create_consultation_invoice(frm) {
	frappe.call({
		method: "vetedge.services.billing.create_consultation_invoice",
		args: {
			consultation: frm.doc.name,
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
}

function add_status_actions(frm) {
	if (["Completed", "Cancelled"].includes(frm.doc.status)) {
		return;
	}

	const paymentRequired = frm.doc.payment_status !== "Paid" && frm.doc.status === "Awaiting Payment";
	const transitions = {
		Draft: [
			[__("Start Consultation"), "In Progress"],
			[__("Cancel Consultation"), "Cancelled"],
		],
		"In Progress": [
			[__("Mark Ready for Treatment"), "Ready for Treatment"],
			[__("Complete Consultation"), "Completed"],
			[__("Cancel Consultation"), "Cancelled"],
		],
		"Awaiting Payment": [
			[__("Complete Consultation"), "Completed"],
			[__("Cancel Consultation"), "Cancelled"],
		],
		"Pending Dispensary": [
			[__("Complete Consultation"), "Completed"],
			[__("Cancel Consultation"), "Cancelled"],
		],
		"Ready for Treatment": [
			[__("Complete Consultation"), "Completed"],
			[__("Cancel Consultation"), "Cancelled"],
		],
	};

	(transitions[frm.doc.status] || [])
		.filter(([, status]) => !(paymentRequired && ["Pending Dispensary", "Ready for Treatment", "Completed"].includes(status)))
		.forEach(([label, status]) => {
		frm.add_custom_button(label, () => {
			transition_consultation(frm, status);
		}, __("Status"));
	});
}

function add_dispensary_actions(frm) {
	if (frm.doc.dispensary_stock_entry) {
		frm.add_custom_button(__("Open Stock Entry"), () => {
			frappe.set_route("Form", "Stock Entry", frm.doc.dispensary_stock_entry);
		}, __("Dispensary"));
	}

	if (
		["Completed", "Cancelled"].includes(frm.doc.status) ||
		frm.doc.dispensary_status !== "Pending Dispensary"
	) {
		return;
	}

	frm.add_custom_button(__("Confirm Dispensary Issue"), () => {
		frappe.call({
			method: "vetedge.services.dispensary.confirm_dispensary_issue",
			args: {
				consultation: frm.doc.name,
				dispensed_items: frm.doc.dispensed_treatments || [],
			},
			freeze: true,
			freeze_message: __("Confirming dispensary issue..."),
			callback(result) {
				if (!result.message?.consultation) {
					return;
				}
				frappe.show_alert({
					message: __("Dispensary issue confirmed"),
					indicator: "green",
				});
				frm.reload_doc();
			},
		});
	}, __("Dispensary"));
}

function transition_consultation(frm, status) {
	frappe.call({
		method: "vetedge.services.consultation_flow.transition_consultation_status",
		args: {
			consultation: frm.doc.name,
			status,
		},
		freeze: true,
		freeze_message: __("Updating consultation..."),
		callback() {
			frappe.show_alert({
				message: __("Consultation updated"),
				indicator: "green",
			});
			frm.reload_doc();
		},
	});
}

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

function show_follow_up_appointment_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Create Follow-up Appointment"),
		fields: [
			{
				fieldname: "appointment_datetime",
				fieldtype: "Datetime",
				label: __("Appointment Date/Time"),
				default: frm.doc.follow_up_date
					? `${frm.doc.follow_up_date} 09:00:00`
					: frappe.datetime.now_datetime(),
				reqd: 1,
			},
			{
				fieldname: "notes",
				fieldtype: "Small Text",
				label: __("Notes"),
				default: frm.doc.treatment_plan_summary || "",
			},
		],
		primary_action_label: __("Create Appointment"),
		primary_action(values) {
			frappe.call({
				method: "vetedge.services.appointment_flow.create_follow_up_from_consultation",
				args: {
					consultation: frm.doc.name,
					appointment_datetime: values.appointment_datetime,
					notes: values.notes,
				},
				freeze: true,
				freeze_message: __("Creating follow-up appointment..."),
				callback(result) {
					const appointment = result.message;
					if (!appointment?.name) {
						return;
					}

					dialog.hide();
					if (frm.fields_dict.follow_up_appointment) {
						frm.set_value("follow_up_appointment", appointment.name);
						frm.save_or_update().then(() => frm.reload_doc());
					}
					frappe.show_alert({
						message: __("Follow-up appointment created"),
						indicator: "green",
					});
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
