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

		frm.set_query("consulting_practitioner", () => ({
			query: "vetedge.services.permissions.get_veterinary_doctor_users",
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
			query: "vetedge.services.treatment_items.get_treatment_item_link_options",
		}));
	},

	refresh(frm) {
		applyCurrentDoctorPractitionerDefault(frm);
		configure_planned_treatments_grid(frm);
		configure_dispensary_grid(frm);
		sync_dispensary_preview(frm);
		frm.add_custom_button(__("View Medical History"), () => {
			show_medical_history_dialog(frm);
		}, __("Clinical"));

		if (!frm.is_new() && frm.doc.patient && frm.doc.service_branch) {
			add_appointment_link_actions(frm);
			add_status_actions(frm);
			add_dispensary_actions(frm);
			add_lab_actions(frm);
			add_hospitalisation_actions(frm);
			try {
				add_vaccination_actions(frm);
			} catch (error) {
				console.error("Failed to initialize vaccination actions", error);
			}

			if (!consultationIsClosed(frm)) {
				frm.add_custom_button(__("New Vitals"), () => {
					show_vitals_entry_dialog(frm);
				}, __("Clinical"));
			}

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

	onload(frm) {
		applyCurrentDoctorPractitionerDefault(frm);
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
		if (consultationScopeIsLocked(frm)) {
			frappe.msgprint(__("This consultation is already Ready for Treatment or beyond. Start a new consultation for additional clinical orders."));
			return;
		}
		sync_dispensary_preview(frm, true);
	},

	planned_treatments_remove(frm) {
		sync_dispensary_preview(frm, true);
	},
});

function add_appointment_link_actions(frm) {
	if (frm.is_new()) {
		return;
	}

	frm.add_custom_button(__("View Appointments"), () => {
		show_appointment_details_dialog(frm);
	}, __("Appointment"));
}

function show_appointment_details_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Appointment Details"),
		size: "large",
		fields: [{ fieldtype: "HTML", fieldname: "body" }],
		primary_action_label: __("Close"),
		primary_action() {
			dialog.hide();
		},
	});

	function render_loading() {
		dialog.fields_dict.body.$wrapper.html(`<div class="text-muted">${__("Loading appointment details...")}</div>`);
	}

	function render_empty(message) {
		return `<div class="text-muted">${escape_consultation_history_html(message)}</div>`;
	}

	function detail_row(label, value) {
		return `
			<div class="ve-appointment-row">
				<div class="text-muted">${escape_consultation_history_html(label)}</div>
				<div>${escape_consultation_history_html(value || "-")}</div>
			</div>
		`;
	}

	function format_datetime(value) {
		return value ? frappe.datetime.str_to_user(value) : "";
	}

	function render_appointment_section(title, appointment, empty_message, button_label) {
		if (!appointment) {
			return `
				<div class="ve-appointment-section">
					<h4>${escape_consultation_history_html(title)}</h4>
					${render_empty(empty_message)}
				</div>
			`;
		}

		const type = [appointment.appointment_type, appointment.consultation_type].filter(Boolean).join(" / ");
		return `
			<div class="ve-appointment-section">
				<h4>${escape_consultation_history_html(title)}</h4>
				<div class="ve-appointment-grid">
					${detail_row(__("Appointment ID"), appointment.name)}
					${detail_row(__("Appointment Date/Time"), format_datetime(appointment.appointment_datetime))}
					${detail_row(__("Status"), appointment.status)}
					${detail_row(__("Patient / Animal"), appointment.patient_name || appointment.patient)}
					${detail_row(__("Owner / Customer"), appointment.owner_name || appointment.primary_owner)}
					${detail_row(__("Practitioner"), appointment.practitioner_name || appointment.practitioner)}
					${detail_row(__("Service Branch"), appointment.service_branch)}
					${detail_row(__("Appointment / Consultation Type"), type)}
					${detail_row(__("Source Consultation"), appointment.source_consultation)}
					${detail_row(__("Reason / Notes"), appointment.notes)}
				</div>
				<div class="ve-appointment-actions">
					<button class="btn btn-default btn-sm" data-appointment="${escape_consultation_history_html(appointment.name)}">
						${escape_consultation_history_html(button_label)}
					</button>
				</div>
			</div>
		`;
	}

	function render(summary) {
		const dirtyWarning = frm.is_dirty() && frm.doc.follow_up_date
			? `<div class="alert alert-warning">${__("This consultation has unsaved follow-up date changes. Save the consultation before relying on generated follow-up appointment details.")}</div>`
			: "";
		dialog.fields_dict.body.$wrapper.html(`
			<style>
				.ve-appointment-section { margin-bottom: 18px; }
				.ve-appointment-section h4 { margin: 0 0 10px; font-size: 13px; font-weight: 600; }
				.ve-appointment-grid {
					display: grid;
					grid-template-columns: repeat(2, minmax(0, 1fr));
					gap: 10px 18px;
				}
				.ve-appointment-row > div:last-child { font-weight: 500; word-break: break-word; }
				.ve-appointment-actions { margin-top: 12px; }
				@media (max-width: 767px) {
					.ve-appointment-grid { grid-template-columns: 1fr; }
				}
			</style>
			${dirtyWarning}
			${render_appointment_section(
				__("Service Appointment"),
				summary.service_appointment,
				__("No service appointment linked to this consultation."),
				__("Open Appointment")
			)}
			${render_appointment_section(
				__("Follow-up Appointment"),
				summary.follow_up_appointment,
				__("No follow-up appointment created yet."),
				__("Open Follow-up Appointment")
			)}
		`);

		dialog.fields_dict.body.$wrapper.find("[data-appointment]").on("click", function () {
			const appointment = $(this).attr("data-appointment");
			if (appointment) {
				frappe.set_route("Form", "Veterinary Appointment", appointment);
			}
		});
	}

	dialog.show();
	render_loading();
	frappe.call({
		method: "vetedge.services.consultation_flow.get_consultation_appointment_summary",
		args: { consultation: frm.doc.name },
		callback(result) {
			render(result.message || {});
		},
	});
}

function show_medical_history_dialog(frm) {
	if (!frm.doc.patient) {
		frappe.msgprint(__("Select a patient/animal before viewing medical history."));
		return;
	}

	const dialog = new frappe.ui.Dialog({
		title: __("Medical History"),
		size: "extra-large",
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "history_html",
				options: `<p class="text-muted">${__("Loading medical history...")}</p>`,
			},
		],
	});

	dialog.show();

	frappe.call({
		method: "vetedge.services.medical_history.get_patient_medical_history_view",
		args: {
			patient: frm.doc.patient,
			limit: 20,
		},
		freeze: true,
		freeze_message: __("Loading medical history..."),
		callback(response) {
			const data = response?.message || {};
			dialog.fields_dict.history_html.$wrapper.html(render_consultation_medical_history(data));
		},
		error() {
			dialog.fields_dict.history_html.$wrapper.html(
				`<p class="text-danger">${__("Unable to load medical history.")}</p>`
			);
		},
	});
}

function render_consultation_medical_history(data) {
	const summary = data.summary || {};
	return `
		<div class="vetedge-consultation-history-popup">
			<div class="mb-3">
				<h5>${escape_consultation_history_html(summary.patient_name || data.patient || __("Patient"))}</h5>
				<div class="row">
					${history_summary_item(__("Species"), summary.species)}
					${history_summary_item(__("Breed"), summary.breed)}
					${history_summary_item(__("Owner"), summary.primary_owner)}
					${history_summary_item(__("Default Branch"), summary.default_branch)}
				</div>
			</div>
			${history_consultation_section(data.consultations || [])}
			${history_simple_section(__("Vaccinations"), data.vaccinations || [], [
				[__("Date/Time"), "timestamp", format_history_datetime],
				[__("Vaccine"), "vaccine"],
				[__("Status"), "status"],
				[__("Next Due"), "next_due_date"],
			])}
			${history_simple_section(__("Lab History"), data.labs || [], [
				[__("Requested On"), "timestamp", format_history_datetime],
				[__("Order"), "name"],
				[__("Status"), "status"],
				[__("Tests"), "tests_summary"],
				[__("Results"), "results_summary"],
			])}
			${history_simple_section(__("Treatment History"), data.treatments || [], [
				[__("Date/Time"), "timestamp", format_history_datetime],
				[__("Item"), "item"],
				[__("Qty"), "qty"],
				[__("UOM"), "uom"],
				[__("Branch"), "service_branch"],
			])}
		</div>
	`;
}

function history_summary_item(label, value) {
	return `
		<div class="col-md-3 mb-2">
			<div class="text-muted">${label}</div>
			<div>${escape_consultation_history_html(value || __("Not Set"))}</div>
		</div>
	`;
}

function history_consultation_section(rows) {
	if (!rows.length) {
		return history_empty_section(__("Previous Consultations"));
	}
	return `
		<div class="mb-4">
			<h5>${__("Previous Consultations")}</h5>
			${rows
				.map(
					(row) => `
						<div class="border rounded p-3 mb-3">
							<div class="d-flex flex-wrap justify-content-between gap-2">
								<strong>${escape_consultation_history_html(row.title || row.name)}</strong>
								<span class="text-muted">${escape_consultation_history_html(format_history_datetime(row.timestamp))}</span>
							</div>
							<div class="text-muted mb-2">
								${escape_consultation_history_html(row.practitioner || __("Not Set"))}
								${row.service_branch ? ` | ${escape_consultation_history_html(row.service_branch)}` : ""}
								${row.status ? ` | ${escape_consultation_history_html(row.status)}` : ""}
							</div>
							${history_rich_block(__("Assessment"), row.assessment_notes)}
							${history_treatment_plan_block(row)}
							${row.follow_up_date ? `<div><strong>${__("Follow-up")}</strong>: ${escape_consultation_history_html(row.follow_up_date)}</div>` : ""}
						</div>`
				)
				.join("")}
		</div>
	`;
}

function history_treatment_plan_block(row) {
	const parts = [];
	const summary = sanitize_consultation_history_rich_text(row.treatment_plan_summary);
	if (summary) {
		parts.push(`<div class="mb-2">${summary}</div>`);
	}
	return `
		<div class="mb-2">
			<strong>${__("Treatment Plan")}</strong>
			<div>${parts.join("") || `<span class="text-muted">${__("No treatment plan recorded")}</span>`}</div>
		</div>
	`;
}

function history_rich_block(label, value) {
	const html = sanitize_consultation_history_rich_text(value);
	return `
		<div class="mb-2">
			<strong>${label}</strong>
			<div>${html || `<span class="text-muted">${__("Not Set")}</span>`}</div>
		</div>
	`;
}

function history_simple_section(title, rows, columns) {
	if (!rows.length) {
		return history_empty_section(title);
	}
	const header = columns.map(([label]) => `<th>${label}</th>`).join("");
	const body = rows
		.map((row) => {
			const cells = columns
				.map(([, fieldname, formatter]) => {
					const value = formatter ? formatter(row[fieldname], row) : row[fieldname];
					return `<td>${escape_consultation_history_html(value || "")}</td>`;
				})
				.join("");
			return `<tr>${cells}</tr>`;
		})
		.join("");
	return `
		<div class="mb-4">
			<h5>${title}</h5>
			<div class="table-responsive">
				<table class="table table-bordered table-sm">
					<thead><tr>${header}</tr></thead>
					<tbody>${body}</tbody>
				</table>
			</div>
		</div>
	`;
}

function history_empty_section(title) {
	return `
		<div class="mb-4">
			<h5>${title}</h5>
			<p class="text-muted">${__("No records found.")}</p>
		</div>
	`;
}

function format_history_datetime(value) {
	return value ? frappe.datetime.str_to_user(value) : "";
}

function sanitize_consultation_history_rich_text(value) {
	if (!value) {
		return "";
	}
	const container = document.createElement("div");
	container.innerHTML = String(value);
	container.querySelectorAll("script, style, iframe, object, embed, link, meta").forEach((node) => node.remove());
	container.querySelectorAll("*").forEach((node) => {
		[...node.attributes].forEach((attribute) => {
			const name = attribute.name.toLowerCase();
			const val = attribute.value || "";
			if (name.startsWith("on") || (["href", "src", "xlink:href"].includes(name) && /^\s*javascript:/i.test(val))) {
				node.removeAttribute(attribute.name);
			}
		});
	});
	return container.innerHTML;
}

function escape_consultation_history_html(value) {
	if (value === undefined || value === null) {
		return "";
	}
	return frappe.utils.escape_html(String(value));
}

function applyCurrentDoctorPractitionerDefault(frm) {
	if (!frm.is_new() || frm.doc.consulting_practitioner || frm.doc.linked_appointment) {
		return;
	}

	if (!frappe.user.has_role("VetEdge Doctor")) {
		return;
	}

	frm.set_value("consulting_practitioner", frappe.session.user);
}

function consultationScopeIsLocked(frm) {
	return ["Ready for Treatment", "Completed", "Cancelled"].includes(frm.doc.status);
}

function consultationIsClosed(frm) {
	return ["Completed", "Cancelled"].includes(frm.doc.status);
}

function configure_planned_treatments_grid(frm) {
	const grid = frm.get_field("planned_treatments")?.grid;
	if (!grid) {
		return;
	}

	const locked = consultationScopeIsLocked(frm);
	grid.cannot_add_rows = locked;
	grid.wrapper.find(".grid-add-row, .grid-remove-rows").toggle(!locked);
	frm.set_df_property("planned_treatments", "read_only", locked ? 1 : 0);
	frm.refresh_field("planned_treatments");
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
			update_planned_treatment_amount(cdt, cdn);
		});

		frappe.call({
			method: "vetedge.services.treatment_items.get_treatment_item_defaults_for_consultation",
			args: {
				item_code: row.item,
				company: frm.doc.company,
				customer: frm.doc.primary_owner,
				branch: frm.doc.service_branch,
			},
			callback(result) {
				const defaults = result.message || {};
				if (!row.uom && defaults.uom) {
					frappe.model.set_value(cdt, cdn, "uom", defaults.uom);
				}
				if (!flt(row.rate) && defaults.rate != null) {
					frappe.model.set_value(cdt, cdn, "rate", flt(defaults.rate));
				}
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

function add_hospitalisation_actions(frm) {
	if (["Completed", "Cancelled"].includes(frm.doc.status)) {
		return;
	}

	frappe.db
		.get_single_value("Veterinary Settings", "enable_veterinary_hospitalisation")
		.then((enabled) => {
			if (!enabled) {
				return;
			}
			frm.add_custom_button(__("Admit for Hospitalisation"), () => {
				frappe.call({
					method: "vetedge.services.hospitalisation.create_hospitalisation_from_consultation",
					args: { consultation_name: frm.doc.name },
					freeze: true,
					freeze_message: __("Creating hospitalisation..."),
					callback(result) {
						if (result.message) {
							frappe.set_route("Form", "Veterinary Hospitalisation", result.message);
						}
					},
				});
			}, __("Clinical"));
		});
}

function add_billing_actions(frm) {
	if (frm.doc.status !== "Cancelled") {
		frm.add_custom_button(__("Billing / Payment"), () => {
			if (window.vetedgeBillingModal?.open) {
				window.vetedgeBillingModal.open(frm);
				return;
			}
			frappe.msgprint(__("Billing modal helper is not available. Please refresh the page."));
		}, __("Billing"));
	}
}

function add_lab_actions(frm) {
	if (frm.doc.status === "Cancelled") {
		return;
	}

	if (!consultationScopeIsLocked(frm)) {
		frm.add_custom_button(__("Add New Lab Order"), () => {
			open_lab_order_dialog_safely(frm);
		}, __("Clinical"));
	}

	frm.add_custom_button(__("View Lab Orders"), () => {
		show_consultation_lab_orders_dialog(frm);
	}, __("Clinical"));
}

function show_consultation_lab_orders_dialog(frm) {
	frappe.call({
		method: "vetedge.services.lab.get_consultation_lab_orders_for_popup",
		args: {
			consultation: frm.doc.name,
		},
		callback(result) {
			const orders = result.message || [];
			const dialog = new frappe.ui.Dialog({
				title: __("Consultation Lab Orders"),
				fields: [
					{
						fieldname: "status_filter",
						fieldtype: "Select",
						label: __("Status"),
						options: [
							"",
							"Draft",
							"Requested",
							"Sample Collected",
							"In Progress",
							"Result Entered",
							"Reviewed",
							"Cancelled",
						].join("\n"),
						change() {
							render_lab_order_results(frm, dialog, orders);
						},
					},
					{
						fieldname: "search_text",
						fieldtype: "Data",
						label: __("Search"),
						change() {
							render_lab_order_results(frm, dialog, orders);
						},
					},
					{
						fieldname: "results_html",
						fieldtype: "HTML",
					},
				],
				primary_action_label: __("Close"),
				primary_action() {
					dialog.hide();
				},
			});

			dialog.show();
			render_lab_order_results(frm, dialog, orders);
		},
	});
}

function show_lab_order_dialog(frm) {
	frappe.call({
		method: "vetedge.services.lab.get_active_lab_tests_for_picker",
		callback(result) {
			const tests = result.message || [];
			const state = {
				selected: [],
			};
			const dialog = new frappe.ui.Dialog({
				title: __("New Lab Order"),
				fields: [
					{
						fieldname: "sample_notes",
						fieldtype: "Small Text",
						label: __("Sample Notes"),
					},
					{
						fieldname: "search_text",
						fieldtype: "Data",
						label: __("Search Lab Tests"),
						change() {
							render_lab_test_picker(dialog, tests, state);
						},
					},
					{
						fieldname: "selected_html",
						fieldtype: "HTML",
					},
					{
						fieldname: "results_html",
						fieldtype: "HTML",
					},
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
							consultation: frm.doc.name,
							sample_notes: values.sample_notes,
							lab_tests: state.selected.map((name) => ({ lab_test_template: name })),
						},
						freeze: true,
						freeze_message: __("Creating lab order..."),
						callback(response) {
							if (!response.message?.name) {
								return;
							}
							dialog.hide();
							frappe.show_alert({
								message: __("Lab order created"),
								indicator: "green",
							});
							frm.reload_doc();
							show_lab_order_summary_dialog(frm, response.message.name);
						},
					});
				},
			});

			dialog.show();
			render_lab_test_picker(dialog, tests, state);
		},
	});
}

function render_lab_order_results(frm, dialog, orders) {
	const statusFilter = dialog.get_value("status_filter");
	const searchText = (dialog.get_value("search_text") || "").trim().toLowerCase();
	const rows = (orders || []).filter((row) => {
		if (statusFilter && row.status !== statusFilter) {
			return false;
		}
		if (!searchText) {
			return true;
		}
		return [row.name, row.lab_order_title, row.status, row.requested_by]
			.filter(Boolean)
			.some((value) => String(value).toLowerCase().includes(searchText));
	});

	const wrapper = dialog.fields_dict.results_html.$wrapper;
	if (!rows.length) {
		wrapper.html(`<div class="text-muted small">${__("No lab orders found for this consultation.")}</div>`);
		return;
	}

	const html = rows
		.map((row) => {
			const requestedOn = row.requested_on
				? frappe.datetime.str_to_user(row.requested_on)
				: __("Unknown");
			return `
				<div class="lab-order-popup-row" data-name="${frappe.utils.escape_html(row.name)}" style="border: 1px solid var(--border-color); border-radius: 10px; padding: 12px; margin-bottom: 10px; cursor: pointer;">
					<div style="display: flex; justify-content: space-between; gap: 12px; align-items: center;">
						<div>
							<div style="font-weight: 600;">${frappe.utils.escape_html(row.lab_order_title || row.name)}</div>
							<div class="text-muted small">${frappe.utils.escape_html(row.name)}</div>
						</div>
						<div style="text-align: right;">
							<div class="indicator-pill ${get_status_pill_class(row.status)}">${__(row.status)}</div>
							<div class="text-muted small" style="margin-top: 6px;">${requestedOn}</div>
						</div>
					</div>
				</div>
			`;
		})
		.join("");

	wrapper.html(html);
	wrapper.find(".lab-order-popup-row").on("click", function () {
		show_lab_order_summary_dialog(frm, $(this).attr("data-name"), () => dialog.hide());
	});
}

function open_lab_order_dialog_safely(frm) {
	if (!frm.is_dirty()) {
		show_lab_order_dialog(frm);
		return;
	}
	frappe.confirm(
		__("Save consultation changes before creating a lab order?"),
		() => frm.save().then(() => show_lab_order_dialog(frm)),
		() => frappe.msgprint(__("Please save or discard consultation changes before creating a lab order."))
	);
}

function render_lab_test_picker(dialog, tests, state) {
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
	const selectedTests = state.selected
		.map((name) => tests.find((test) => test.name === name))
		.filter(Boolean);

	if (selectedTests.length) {
		selectedWrapper.html(`
			<div style="margin-bottom: 12px;">
				<div class="small text-muted" style="margin-bottom: 8px;">${__("Selected Lab Tests")}</div>
				<div style="display: flex; flex-wrap: wrap; gap: 8px;">
					${selectedTests
						.map(
							(test) => `
								<span class="indicator-pill blue" data-remove="${frappe.utils.escape_html(test.name)}" style="cursor: pointer;">
									${frappe.utils.escape_html(test.test_name)}
								</span>
							`
						)
						.join("")}
				</div>
			</div>
		`);
	} else {
		selectedWrapper.html(`<div class="text-muted small" style="margin-bottom: 12px;">${__("No lab tests selected yet.")}</div>`);
	}

	if (!available.length) {
		resultWrapper.html(`<div class="text-muted small">${__("No matching lab tests found.")}</div>`);
	} else {
		resultWrapper.html(
			available
				.map((test) => {
					const isSelected = state.selected.includes(test.name);
					return `
						<div class="lab-test-picker-row" data-name="${frappe.utils.escape_html(test.name)}" style="border: 1px solid var(--border-color); border-radius: 10px; padding: 12px; margin-bottom: 10px; cursor: pointer; background: ${isSelected ? "var(--subtle-fg)" : "var(--card-bg)"};">
							<div style="display: flex; justify-content: space-between; gap: 12px; align-items: center;">
								<div>
									<div style="font-weight: 600;">${frappe.utils.escape_html(test.test_name || test.name)}</div>
									<div class="text-muted small">${frappe.utils.escape_html(test.sample_type || __("Sample type not set"))}</div>
								</div>
								<div class="small ${isSelected ? "text-primary" : "text-muted"}">${isSelected ? __("Selected") : __("Select")}</div>
							</div>
						</div>
					`;
				})
				.join("")
		);
	}

	selectedWrapper.find("[data-remove]").on("click", function () {
		const name = $(this).attr("data-remove");
		state.selected = state.selected.filter((value) => value !== name);
		render_lab_test_picker(dialog, tests, state);
	});

	resultWrapper.find(".lab-test-picker-row").on("click", function () {
		const name = $(this).attr("data-name");
		if (state.selected.includes(name)) {
			state.selected = state.selected.filter((value) => value !== name);
		} else {
			state.selected = [...state.selected, name];
		}
		render_lab_test_picker(dialog, tests, state);
	});
}

function get_status_pill_class(status) {
	return {
		Draft: "gray",
		Requested: "blue",
		"Sample Collected": "orange",
		"In Progress": "yellow",
		"Result Entered": "purple",
		Reviewed: "green",
		Cancelled: "red",
	}[status] || "gray";
}

function show_lab_order_summary_dialog(frm, labOrder, beforeOpen = null) {
	frappe.call({
		method: "vetedge.services.lab.get_lab_order_popup_summary",
		args: { lab_order: labOrder },
		freeze: true,
		freeze_message: __("Loading lab order..."),
		callback(result) {
			const order = result.message;
			if (!order) {
				return;
			}
			if (beforeOpen) {
				beforeOpen();
			}
			const dialog = new frappe.ui.Dialog({
				title: __("Lab Order Details"),
				size: "large",
				fields: [{ fieldtype: "HTML", fieldname: "body" }],
				primary_action_label: __("Close"),
				primary_action() {
					dialog.hide();
				},
			});
			dialog.show();
			render_lab_order_summary(dialog, order);
			dialog.fields_dict.body.$wrapper.find("[data-action='refresh-lab-order']").on("click", () => {
				dialog.hide();
				show_lab_order_summary_dialog(frm, order.name);
			});
			dialog.fields_dict.body.$wrapper.find("[data-action='open-full-lab-order']").on("click", () => {
				frappe.set_route("Form", "Veterinary Lab Order", order.name);
			});
		},
	});
}

function render_lab_order_summary(dialog, order) {
	const tests = order.lab_tests || [];
	const invoice = order.invoice;
	const requestedOn = order.requested_on ? frappe.datetime.str_to_user(order.requested_on) : "";
	dialog.fields_dict.body.$wrapper.html(`
		<div>
			<div style="display: flex; justify-content: space-between; gap: 12px;">
				<div>
					<div style="font-weight: 600;">${frappe.utils.escape_html(order.title || order.name)}</div>
					<div class="text-muted small">${frappe.utils.escape_html(order.name)}</div>
				</div>
				<div style="text-align: right;">
					<div class="indicator-pill ${get_status_pill_class(order.status)}">${__(order.status)}</div>
					<div class="text-muted small" style="margin-top: 6px;">${frappe.utils.escape_html(requestedOn)}</div>
				</div>
			</div>
			<hr>
			<div style="display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 18px;">
				<div><strong>${__("Patient / Animal")}:</strong> ${frappe.utils.escape_html(order.patient || "")}</div>
				<div><strong>${__("Owner / Customer")}:</strong> ${frappe.utils.escape_html(order.primary_owner || "")}</div>
				<div><strong>${__("Consultation")}:</strong> ${frappe.utils.escape_html(order.consultation || "")}</div>
				<div><strong>${__("Practitioner")}:</strong> ${frappe.utils.escape_html(order.requested_by || "")}</div>
				<div><strong>${__("Service Branch")}:</strong> ${frappe.utils.escape_html(order.service_branch || "")}</div>
			</div>
			<div style="margin-top: 14px;">
				<div class="small text-muted" style="margin-bottom: 8px;">${__("Requested Tests / Items")}</div>
				${tests.length ? tests.map((test) => `
					<div style="border: 1px solid var(--border-color); border-radius: 8px; padding: 10px; margin-bottom: 8px;">
						<div style="font-weight: 600;">${frappe.utils.escape_html(test.test_name || test.lab_test_template)}</div>
						<div class="text-muted small">${frappe.utils.escape_html(test.billing_item || __("No billing item"))}</div>
						${test.notes ? `<div class="small">${frappe.utils.escape_html(test.notes)}</div>` : ""}
					</div>
				`).join("") : `<div class="text-muted small">${__("No lab tests recorded.")}</div>`}
			</div>
			<div style="margin-top: 14px;">
				<div class="small text-muted" style="margin-bottom: 8px;">${__("Invoice / Payment")}</div>
				${invoice ? `
					<div><strong>${__("Invoice")}:</strong> ${frappe.utils.escape_html(invoice.name)}</div>
					<div><strong>${__("Status")}:</strong> ${frappe.utils.escape_html(invoice.status || "")}</div>
					<div><strong>${__("Outstanding")}:</strong> ${format_currency(invoice.outstanding_amount || 0, invoice.currency)}</div>
				` : `<div class="text-muted small">${__("No linked invoice yet.")}</div>`}
			</div>
			<div style="display: flex; gap: 8px; margin-top: 16px;">
				<button class="btn btn-default btn-sm" data-action="refresh-lab-order">${__("Refresh")}</button>
				<button class="btn btn-default btn-sm" data-action="open-full-lab-order">${__("Open Full Lab Order")}</button>
			</div>
		</div>
	`);
}

function getConsultationInvoices(frm) {
	const rows = (frm.doc.consultation_invoices || []).map((row) => ({
		name: row.sales_invoice,
		status: row.invoice_status,
		posting_date: row.posting_date,
		currency: row.currency,
		grand_total: row.grand_total,
		outstanding_amount: row.outstanding_amount,
	})).filter((row) => row.name);

	if (!rows.length && frm.doc.linked_invoice) {
		rows.push({ name: frm.doc.linked_invoice, status: frm.doc.payment_status });
	}

	return rows;
}

function showConsultationInvoicesDialog(invoices) {
	const rows = (invoices || []).filter((row) => row?.name);
	if (!rows.length) {
		frappe.msgprint(__("No invoice is linked yet."));
		return;
	}

	const dialog = new frappe.ui.Dialog({
		title: __("Consultation Invoices"),
		fields: [{ fieldname: "history_html", fieldtype: "HTML" }],
		primary_action_label: __("Close"),
		primary_action() {
			dialog.hide();
		},
	});

	dialog.fields_dict.history_html.$wrapper.html(renderConsultationInvoiceHistory(rows));
	dialog.fields_dict.history_html.$wrapper.find("[data-invoice-name]").on("click", function () {
		const invoiceName = $(this).attr("data-invoice-name");
		dialog.hide();
		if (window.vetedgeInvoiceSummary?.open) {
			window.vetedgeInvoiceSummary.open(invoiceName);
			return;
		}
		frappe.msgprint(__("Invoice summary helper is not available. Please refresh the page."));
	});
	dialog.show();
}

function renderConsultationInvoiceHistory(invoices) {
	return `
		<div class="vetedge-invoice-history">
			${invoices
				.map((invoice) => {
					const currency = invoice.currency || frappe.defaults.get_default("currency");
					const total = format_currency(invoice.grand_total || 0, currency);
					const outstanding = format_currency(invoice.outstanding_amount || 0, currency);
					const postingDate = invoice.posting_date ? frappe.datetime.str_to_user(invoice.posting_date) : __("Unknown");

					return `
						<div class="frappe-card p-3 mb-3" data-invoice-name="${frappe.utils.escape_html(invoice.name)}" style="cursor: pointer;">
							<div class="d-flex justify-content-between align-items-start gap-3">
								<div>
									<div class="small text-muted mb-1">${__("Invoice")}</div>
									<div class="h6 mb-1">${frappe.utils.escape_html(invoice.name)}</div>
									<div class="text-muted small">${postingDate}</div>
								</div>
								<div class="text-end">
									<div class="indicator-pill ${getConsultationInvoicePill(invoice.status)}">${__(invoice.status || "Unknown")}</div>
									<div class="small text-muted mt-2">${__("Outstanding")}: ${outstanding}</div>
									<div class="small text-muted">${__("Total")}: ${total}</div>
								</div>
							</div>
						</div>
					`;
				})
				.join("")}
			<div class="text-muted small">${__("Click an invoice to review the summary and open the ERPNext form in a new tab.")}</div>
		</div>
	`;
}

function getConsultationInvoicePill(status) {
	return {
		Draft: "gray",
		Submitted: "blue",
		Unpaid: "orange",
		"Partly Paid": "yellow",
		Paid: "green",
		Overdue: "red",
		Cancelled: "red",
		"Credit Note Issued": "purple",
		"Internal Transfer": "cyan",
	}[status] || "gray";
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
	if (status === "Cancelled") {
		show_consultation_cancellation_preflight(frm);
		return;
	}
	perform_consultation_status_transition(frm, status);
}

function show_consultation_cancellation_preflight(frm) {
	frappe.call({
		method: "vetedge.services.consultation_cancellation.get_consultation_cancellation_preflight",
		args: {
			consultation_name: frm.doc.name,
		},
		freeze: true,
		freeze_message: __("Checking cancellation safety..."),
		callback(result) {
			const preflight = result.message || {};
			show_consultation_cancellation_dialog(frm, preflight);
		},
	});
}

function show_consultation_cancellation_dialog(frm, preflight) {
	const canCancel = Boolean(preflight.can_cancel);
	const dialog = new frappe.ui.Dialog({
		title: canCancel ? __("Confirm Consultation Cancellation") : __("Consultation Cancellation Preflight"),
		size: "extra-large",
		fields: [{ fieldtype: "HTML", fieldname: "preflight_html" }],
		primary_action_label: canCancel ? __("Cancel Consultation") : __("Close"),
		primary_action() {
			if (!canCancel) {
				dialog.hide();
				return;
			}
			frappe.confirm(__("Cancel this consultation now?"), () => {
				dialog.hide();
				perform_safe_consultation_cancellation(frm);
			});
		},
		secondary_action_label: __("Close"),
		secondary_action() {
			dialog.hide();
		},
	});

	dialog.fields_dict.preflight_html.$wrapper.html(render_consultation_cancellation_preflight(preflight));
	dialog.fields_dict.preflight_html.$wrapper.find("[data-resolution-action]").on("click", function () {
		const action = $(this).attr("data-resolution-action");
		const label = $(this).text();
		show_consultation_resolution_decision_dialog(frm, dialog, action, label);
	});
	dialog.fields_dict.preflight_html.$wrapper.find("[data-retain-payment-cancel]").on("click", function () {
		show_retain_payment_cancellation_confirmation(frm, dialog);
	});
	dialog.fields_dict.preflight_html.$wrapper.find("[data-approve-cancellation-resolution]").on("click", function () {
		const resolution = $(this).attr("data-approve-cancellation-resolution");
		show_cancellation_resolution_approval_dialog(frm, dialog, resolution);
	});
	dialog.fields_dict.preflight_html.$wrapper.find("[data-execute-reschedule-resolution]").on("click", function () {
		const resolution = $(this).attr("data-execute-reschedule-resolution");
		show_reschedule_resolution_dialog(frm, dialog, resolution);
	});
	dialog.fields_dict.preflight_html.$wrapper.find("[data-complete-manual-accounting-resolution]").on("click", function () {
		const resolution = $(this).attr("data-complete-manual-accounting-resolution");
		const label = $(this).attr("data-completion-label");
		show_manual_accounting_resolution_completion_dialog(frm, dialog, preflight.existing_resolution, resolution, label);
	});
	dialog.show();
}

function render_consultation_cancellation_preflight(preflight) {
	const canCancel = Boolean(preflight.can_cancel);
	const summary = canCancel
		? __("Cancellation appears safe. No submitted invoice, payment, stock, or active linked clinical dependency was found.")
		: get_consultation_cancellation_blocked_summary(preflight);
	const statusClass = canCancel ? "alert-success" : "alert-danger";

	return `
		<div class="vetedge-cancellation-preflight">
			<style>
				.ve-cancel-section { margin-bottom: 18px; }
				.ve-cancel-section h4 { margin: 0 0 10px; font-size: 13px; font-weight: 600; }
				.ve-cancel-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 16px; }
				.ve-cancel-card { border: 1px solid var(--border-color); border-radius: 6px; padding: 10px 12px; margin-bottom: 8px; }
				.ve-cancel-card-title { font-weight: 600; word-break: break-word; }
				.ve-cancel-meta { color: var(--text-muted); font-size: 12px; margin-top: 3px; }
				.ve-cancel-actions { display: flex; flex-wrap: wrap; gap: 8px; }
				@media (max-width: 767px) { .ve-cancel-grid { grid-template-columns: 1fr; } }
			</style>
			<div class="alert ${statusClass}">
				<strong>${canCancel ? __("Safe to cancel") : __("Cannot cancel directly")}</strong>
				<div>${escape_consultation_history_html(summary)}</div>
			</div>
			${render_cancellation_blockers(preflight.blockers || [])}
			${render_cancellation_warnings(preflight.warnings || [])}
			${render_cancellation_invoice_section(preflight.linked_invoices || [])}
			${render_cancellation_dependency_sections(preflight)}
			${render_existing_cancellation_resolution(preflight.existing_resolution)}
			${render_cancellation_resolution_actions(preflight.allowed_action_options || [], canCancel)}
			${render_cancellation_patient_outstanding_context(preflight.outstanding_context || [])}
		</div>
	`;
}

function get_consultation_cancellation_blocked_summary(preflight) {
	const summary = preflight.billing_group_summary || {};
	if (flt(summary.paid_amount) > 0) {
		return __("This consultation cannot be cancelled directly because payment or submitted invoices exist. Choose a financial resolution before cancellation.");
	}
	const hasSubmittedInvoice = (preflight.linked_invoices || []).some((row) => cint(row.docstatus) === 1);
	if (hasSubmittedInvoice) {
		return __("This consultation has a submitted invoice. Submitted invoices cannot be changed automatically. Please resolve the invoice through accounts/admin before cancellation.");
	}
	return __("Resolve the listed blockers before cancelling this consultation.");
}

function render_cancellation_blockers(blockers) {
	if (!blockers.length) {
		return "";
	}
	return render_cancellation_card_section(__("Blockers"), blockers.map((row) => ({
		title: row.display_label || row.document || row.invoice || row.type,
		meta: row.status || row.type,
		message: row.message,
	})));
}

function render_cancellation_warnings(warnings) {
	if (!warnings.length) {
		return "";
	}
	return render_cancellation_card_section(__("Warnings"), warnings.map((row) => ({
		title: row.display_label || row.document || row.invoice || row.source_document || row.type,
		meta: row.status || row.type,
		message: row.message,
	})));
}

function render_cancellation_invoice_section(invoices) {
	if (!invoices.length) {
		return "";
	}
	return `
		<div class="ve-cancel-section">
			<h4>${__("Blocking Invoices")}</h4>
			<div class="ve-cancel-grid">
				${invoices.map(render_cancellation_invoice_card).join("")}
			</div>
		</div>
	`;
}

function render_cancellation_invoice_card(invoice) {
	const currency = invoice.currency || frappe.defaults.get_default("currency");
	const total = format_currency(flt(invoice.grand_total), currency);
	const paid = format_currency(flt(invoice.paid_amount), currency);
	const outstanding = format_currency(flt(invoice.outstanding_amount), currency);
	const status = invoice.payment_state || invoice.status || __("Unknown");
	const reason = cint(invoice.docstatus) === 1
		? __("Submitted invoice requires accounts/admin resolution.")
		: __("Draft invoice should be cleaned up through Billing Core if cancellation proceeds.");
	return `
		<div class="ve-cancel-card">
			<div class="ve-cancel-card-title">${escape_consultation_history_html(invoice.invoice || invoice.name)}</div>
			<div class="ve-cancel-meta">${escape_consultation_history_html(status)}</div>
			<div class="ve-cancel-meta">${__("Total")}: ${total} | ${__("Paid")}: ${paid} | ${__("Outstanding")}: ${outstanding}</div>
			<div class="ve-cancel-meta">${escape_consultation_history_html(reason)}</div>
		</div>
	`;
}

function render_cancellation_dependency_sections(preflight) {
	const sections = [
		[__("Lab Orders"), preflight.linked_lab_orders || [], "name"],
		[__("Vaccination Records"), preflight.linked_vaccinations || [], "name"],
		[__("Hospitalisation Records"), preflight.linked_hospitalisations || [], "name"],
		[__("Stock Entries"), preflight.linked_stock_entries || [], "name"],
		[__("Billing Sessions"), preflight.linked_billing_sessions || [], "name"],
		[__("Notification Items"), preflight.linked_notifications || [], "name"],
		[__("Planned Treatment Source Rows"), preflight.linked_planned_treatments || [], "name"],
	];
	return sections
		.filter(([, rows]) => rows.length)
		.map(([title, rows, nameField]) => render_cancellation_card_section(
			title,
			rows.map((row) => ({
				title: row.display_label || row[nameField] || row.document || row.source_document || row.item || row.type,
				meta: row.status || row.payment_status || row.billing_status || row.docstatus || row.source_type,
				message: row.message || row.description || row.source_document || "",
			}))
		))
		.join("");
}

function render_cancellation_resolution_actions(options, canCancel) {
	if (canCancel || !options.length) {
		return "";
	}
	return `
		<div class="ve-cancel-section">
			<h4>${__("Financial Resolution Options")}</h4>
			<p class="text-muted">${__("Submitted accounting documents are not changed automatically. Recording a resolution request does not cancel this consultation.")}</p>
			<div class="ve-cancel-actions">
				${options.map((option) => `
					<button class="btn btn-default btn-sm" type="button" data-resolution-action="${escape_consultation_history_html(option.value)}">
						${escape_consultation_history_html(option.label)}
					</button>
				`).join("")}
			</div>
		</div>
	`;
}

function render_existing_cancellation_resolution(resolution) {
	if (!resolution) {
		return "";
	}
	const canRetainPaymentCancel = resolution.resolution_action_key === "retain_payment_clinical_cancel_only"
		&& resolution.resolution_status === "Approved"
		&& user_can_manage_consultation_cancellation_resolution();
	const canExecuteReschedule = resolution.resolution_action_key === "reschedule_consultation"
		&& resolution.resolution_status === "Approved"
		&& user_can_execute_consultation_reschedule_resolution();
	const manualCompletionLabel = get_manual_accounting_resolution_completion_label(resolution);
	const canCompleteManualAccountingResolution = Boolean(manualCompletionLabel)
		&& resolution.resolution_status === "Approved"
		&& user_can_manage_consultation_cancellation_resolution();
	const canApprove = ["Draft", "Pending Review"].includes(resolution.resolution_status)
		&& user_can_manage_consultation_cancellation_resolution();
	const statusGuidance = {
		"Pending Review": __("Resolution pending approval."),
		Approved: __("Resolution approved. Authorized users may execute the approved next step."),
		Completed: __("Resolution completed."),
		Rejected: __("Resolution rejected."),
		Draft: __("Resolution draft."),
	}[resolution.resolution_status] || "";
	const linkedTargets = [
		resolution.linked_new_appointment ? `${__("New Appointment")}: ${resolution.linked_new_appointment}` : "",
		resolution.linked_new_consultation ? `${__("New Consultation")}: ${resolution.linked_new_consultation}` : "",
	].filter(Boolean);
	return `
		<div class="ve-cancel-section">
			<h4>${__("Recorded Resolution Decision")}</h4>
			<div class="ve-cancel-card">
				<div class="ve-cancel-card-title">${escape_consultation_history_html(resolution.resolution_action || resolution.resolution_action_key || "")}</div>
				<div class="ve-cancel-meta">${__("Status")}: ${escape_consultation_history_html(resolution.resolution_status || "")}</div>
				${statusGuidance ? `<div class="ve-cancel-meta">${escape_consultation_history_html(statusGuidance)}</div>` : ""}
				<div class="ve-cancel-meta">${__("Selected By")}: ${escape_consultation_history_html(resolution.selected_by || "")}</div>
				<div class="ve-cancel-meta">${__("Selected On")}: ${escape_consultation_history_html(resolution.selected_on || "")}</div>
				${resolution.reason ? `<div class="ve-cancel-meta">${__("Reason")}: ${escape_consultation_history_html(resolution.reason)}</div>` : ""}
				${linkedTargets.length ? `<div class="ve-cancel-meta">${linkedTargets.map(escape_consultation_history_html).join(" | ")}</div>` : ""}
				${canApprove ? `
					<div class="mt-3">
						<button class="btn btn-default btn-sm" type="button" data-approve-cancellation-resolution="${escape_consultation_history_html(resolution.name)}">
							${__("Approve Resolution")}
						</button>
					</div>
				` : ""}
				${canRetainPaymentCancel ? `
					<div class="mt-3">
						<button class="btn btn-danger btn-sm" type="button" data-retain-payment-cancel="1">
							${__("Cancel Clinical Record and Retain Payment")}
						</button>
					</div>
				` : ""}
				${canExecuteReschedule ? `
					<div class="mt-3">
						<button class="btn btn-primary btn-sm" type="button" data-execute-reschedule-resolution="${escape_consultation_history_html(resolution.name)}">
							${__("Create Reschedule Appointment")}
						</button>
					</div>
				` : ""}
				${canCompleteManualAccountingResolution ? `
					<div class="mt-3">
						<button class="btn btn-primary btn-sm" type="button" data-complete-manual-accounting-resolution="${escape_consultation_history_html(resolution.name)}" data-completion-label="${escape_consultation_history_html(manualCompletionLabel)}">
							${escape_consultation_history_html(manualCompletionLabel)}
						</button>
					</div>
				` : ""}
			</div>
		</div>
	`;
}

function user_can_manage_consultation_cancellation_resolution() {
	const roles = [
		"System Manager",
		"VetEdge Administrator",
		"Branch Manager",
		"VetEdge Branch Manager",
		"Accounts/Cashier",
		"VetEdge Accounts/Cashier",
		"Accounts User",
		"Accounts Manager",
	];
	return roles.some((role) => frappe.user.has_role(role));
}

function user_can_execute_consultation_reschedule_resolution() {
	const roles = [
		"System Manager",
		"VetEdge Administrator",
		"Branch Manager",
		"VetEdge Branch Manager",
		"Accounts/Cashier",
		"VetEdge Accounts/Cashier",
		"Accounts User",
		"Accounts Manager",
		"VetEdge Front Desk",
	];
	return roles.some((role) => frappe.user.has_role(role));
}

function get_manual_accounting_resolution_completion_label(resolution) {
	if (!resolution) {
		return null;
	}
	return {
		refund_required: __("Mark Refund Resolution Completed"),
		issue_customer_credit: __("Mark Credit Resolution Completed"),
		admin_accounting_correction: __("Mark Admin Correction Completed"),
	}[resolution.resolution_action_key] || null;
}

function get_manual_accounting_resolution_guidance(resolution) {
	return {
		refund_required: __("Record refund accounting evidence before completing this resolution."),
		issue_customer_credit: __("Record credit accounting evidence before completing this resolution."),
		admin_accounting_correction: __("Record accounting correction evidence before completing this resolution."),
	}[resolution?.resolution_action_key] || __("Record accounting evidence before completing this resolution.");
}

function get_manual_accounting_status_outcome_guidance(resolution) {
	return {
		refund_required: __("Choose Cancel only if this refund means the consultation/service will not continue."),
		issue_customer_credit: __("Choose Cancel only if this credit replaces a refund for a cancelled consultation."),
		admin_accounting_correction: __("Admin corrections do not change consultation status in this phase."),
	}[resolution?.resolution_action_key] || __("Accounting completion does not change consultation status unless explicitly selected and allowed.");
}

function render_cancellation_patient_outstanding_context(rows) {
	if (!rows.length) {
		return "";
	}
	return `
		<div class="ve-cancel-section">
			<h4>${__("Other Outstanding Invoices for this Patient")}</h4>
			<p class="text-muted">${__("These invoices belong to this patient/customer but are not part of this consultation billing group. Paying them will not satisfy or cancel this consultation.")}</p>
			<div class="ve-cancel-grid">
				${rows.map(render_patient_outstanding_cancellation_card).join("")}
			</div>
		</div>
	`;
}

function render_patient_outstanding_cancellation_card(invoice) {
	const currency = invoice.currency || frappe.defaults.get_default("currency");
	return `
		<div class="ve-cancel-card">
			<div class="ve-cancel-card-title">${escape_consultation_history_html(invoice.invoice || invoice.name)}</div>
			<div class="ve-cancel-meta">${escape_consultation_history_html(invoice.payment_state || invoice.status || __("Outstanding"))}</div>
			<div class="ve-cancel-meta">${__("Total")}: ${format_currency(flt(invoice.grand_total), currency)}</div>
			<div class="ve-cancel-meta">${__("Outstanding")}: ${format_currency(flt(invoice.outstanding_amount), currency)}</div>
			<div class="ve-cancel-meta">${__("Informational only; not a cancellation blocker.")}</div>
		</div>
	`;
}

function render_cancellation_card_section(title, rows) {
	if (!rows.length) {
		return "";
	}
	return `
		<div class="ve-cancel-section">
			<h4>${title}</h4>
			<div class="ve-cancel-grid">
				${rows.map((row) => `
					<div class="ve-cancel-card">
						<div class="ve-cancel-card-title">${escape_consultation_history_html(row.title || "")}</div>
						${row.meta ? `<div class="ve-cancel-meta">${escape_consultation_history_html(row.meta)}</div>` : ""}
						${row.message ? `<div class="ve-cancel-meta">${escape_consultation_history_html(row.message)}</div>` : ""}
					</div>
				`).join("")}
			</div>
		</div>
	`;
}

function show_consultation_resolution_decision_dialog(frm, preflightDialog, action, label) {
	const dialog = new frappe.ui.Dialog({
		title: __("Record Resolution Request"),
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "guidance",
				options: render_consultation_resolution_guidance(action, label),
			},
			{
				fieldtype: "Small Text",
				fieldname: "reason",
				label: __("Reason / Note"),
				reqd: 1,
			},
		],
		primary_action_label: __("Record Resolution Request"),
		primary_action(values) {
			frappe.call({
				method: "vetedge.services.consultation_cancellation.record_consultation_cancellation_resolution",
				args: {
					consultation_name: frm.doc.name,
					resolution_action: action,
					reason: values.reason,
				},
				freeze: true,
				freeze_message: __("Recording resolution decision..."),
				callback(result) {
					dialog.hide();
					if (preflightDialog) {
						preflightDialog.hide();
					}
					frappe.msgprint({
						title: __("Resolution Request Recorded"),
						indicator: "green",
						message: __("Resolution request recorded for approval. The consultation was not cancelled and accounting documents were not changed."),
					});
					frm.reload_doc();
				},
			});
		},
	});
	dialog.show();
}

function render_consultation_resolution_guidance(action, label) {
	const guidance = {
		retain_payment_clinical_cancel_only: __("Use this only when the clinic intentionally keeps the payment and records a clinical cancellation without changing submitted accounting documents."),
		refund_required: __("Create and process the refund through accounts/admin policy. VetEdge does not create refund Payment Entries automatically in this phase."),
		issue_customer_credit: __("Accounts/admin should issue customer credit or a credit note through the approved accounting workflow."),
		reschedule_consultation: __("Create or update the follow-up appointment/consultation plan. Existing submitted invoices remain unchanged."),
		admin_accounting_correction: __("Accounts/admin must review submitted invoices, payments, and stock documents manually before cancellation."),
		admin_review_required: __("Accounts/admin review is required before this consultation can be cancelled."),
	};
	return `
		<p><strong>${escape_consultation_history_html(label || action)}</strong></p>
		<p>${escape_consultation_history_html(guidance[action] || __("Resolve the listed blockers before cancellation."))}</p>
	`;
}

function show_cancellation_resolution_approval_dialog(frm, preflightDialog, resolutionName) {
	const dialog = new frappe.ui.Dialog({
		title: __("Approve Cancellation Resolution"),
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "guidance",
				options: `<p>${__("Approval authorizes the next step but does not cancel this consultation or change accounting documents.")}</p>`,
			},
			{
				fieldtype: "Small Text",
				fieldname: "note",
				label: __("Approval Note"),
			},
		],
		primary_action_label: __("Approve"),
		primary_action(values) {
			frappe.call({
				method: "vetedge.services.consultation_cancellation.approve_consultation_cancellation_resolution",
				args: {
					resolution_name: resolutionName,
					note: values.note,
				},
				freeze: true,
				freeze_message: __("Approving cancellation resolution..."),
				callback() {
					dialog.hide();
					if (preflightDialog) {
						preflightDialog.hide();
					}
					frappe.msgprint({
						title: __("Cancellation Resolution Approved"),
						indicator: "green",
						message: __("Resolution approved. The consultation was not cancelled. Retained-payment clinical cancellation can now be executed by an authorized user."),
					});
					frm.reload_doc();
				},
			});
		},
	});
	dialog.show();
}

function show_retain_payment_cancellation_confirmation(frm, preflightDialog) {
	frappe.confirm(
		__("This will cancel the clinical consultation only. Submitted invoices and payments will remain unchanged."),
		() => {
			frappe.call({
				method: "vetedge.services.consultation_cancellation.retain_payment_and_cancel_consultation",
				args: {
					consultation_name: frm.doc.name,
				},
				freeze: true,
				freeze_message: __("Cancelling clinical consultation..."),
				callback(result) {
					if (preflightDialog) {
						preflightDialog.hide();
					}
					const message = result.message?.message || __("Clinical consultation cancelled. Payment was retained. No accounting reversal was created.");
					frappe.msgprint({
						title: __("Clinical Consultation Cancelled"),
						indicator: "green",
						message,
					});
					frm.reload_doc();
				},
			});
		}
	);
}

function show_reschedule_resolution_dialog(frm, preflightDialog, resolutionName) {
	const dialog = new frappe.ui.Dialog({
		title: __("Create Reschedule Appointment"),
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "guidance",
				options: `<p>${__("This creates a new appointment linked to the approved reschedule resolution. Original submitted invoices and payments remain unchanged and are not transferred.")}</p>`,
			},
			{
				fieldtype: "Datetime",
				fieldname: "appointment_datetime",
				label: __("New Appointment Date/Time"),
				reqd: 1,
			},
			{
				fieldtype: "Small Text",
				fieldname: "reason",
				label: __("Reschedule Note"),
			},
		],
		primary_action_label: __("Create Reschedule Appointment"),
		primary_action(values) {
			frappe.call({
				method: "vetedge.services.consultation_cancellation.execute_consultation_reschedule_resolution",
				args: {
					consultation_name: frm.doc.name,
					resolution_name: resolutionName,
					appointment_datetime: values.appointment_datetime,
					reason: values.reason,
				},
				freeze: true,
				freeze_message: __("Creating reschedule appointment..."),
				callback(result) {
					dialog.hide();
					if (preflightDialog) {
						preflightDialog.hide();
					}
					const message = result.message || {};
					frappe.msgprint({
						title: __("Consultation Rescheduled"),
						indicator: "green",
						message: `${escape_consultation_history_html(message.message || __("Consultation rescheduled. Original invoices and payments were preserved."))}<br>${__("New Appointment")}: ${escape_consultation_history_html(message.linked_new_appointment || "")}`,
					});
					frm.reload_doc();
				},
			});
		},
	});
	dialog.show();
}

function show_manual_accounting_resolution_completion_dialog(frm, preflightDialog, resolution, resolutionName, label) {
	const requiresAmount = ["refund_required", "issue_customer_credit"].includes(resolution?.resolution_action_key);
	const canCancelAfterFinancialResolution = ["refund_required", "issue_customer_credit"].includes(resolution?.resolution_action_key);
	const dialog = new frappe.ui.Dialog({
		title: label || __("Mark Accounting Resolution Completed"),
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "guidance",
				options: `
					<p>${escape_consultation_history_html(get_manual_accounting_resolution_guidance(resolution))}</p>
					<p class="text-muted">${__("This records audit evidence only. VetEdge will not create refunds, Credit Notes, Payment Entries, accounting reversals, or apply credit to a rescheduled consultation.")}</p>
					<p class="text-muted">${escape_consultation_history_html(get_manual_accounting_status_outcome_guidance(resolution))}</p>
				`,
			},
			{
				fieldtype: "Select",
				fieldname: "accounting_reference_doctype",
				label: __("Accounting Reference Type"),
				options: [
					"Payment Entry",
					"Journal Entry",
					"Sales Invoice",
					"Stock Entry",
					"External Reference",
				].join("\n"),
				reqd: 1,
			},
			{
				fieldtype: "Data",
				fieldname: "accounting_reference_name",
				label: __("Accounting Reference"),
				reqd: 1,
			},
			{
				fieldtype: "Currency",
				fieldname: "resolution_amount",
				label: resolution?.resolution_action_key === "issue_customer_credit" ? __("Credit Amount") : __("Refund Amount"),
				reqd: requiresAmount ? 1 : 0,
				hidden: requiresAmount ? 0 : 1,
			},
			{
				fieldtype: "Date",
				fieldname: "resolution_date",
				label: __("Resolution Date"),
				default: frappe.datetime.get_today(),
				reqd: 1,
			},
			{
				fieldtype: "Check",
				fieldname: "external_reference",
				label: __("External/manual reference approved by System Manager or Accounts Manager"),
			},
			{
				fieldtype: "Select",
				fieldname: "status_outcome",
				label: __("After recording this accounting resolution, what should happen to the consultation?"),
				options: canCancelAfterFinancialResolution
					? [
						"No Status Change",
						"Cancel Consultation After Financial Resolution",
					].join("\n")
					: "No Status Change",
				default: "No Status Change",
				reqd: 1,
				description: canCancelAfterFinancialResolution
					? __("Choose Cancel only when the refund or credit means this consultation/service will not continue.")
					: __("Admin corrections do not change consultation status in this phase."),
			},
			{
				fieldtype: "Small Text",
				fieldname: "completion_note",
				label: __("Completion Note"),
				reqd: 1,
			},
		],
		primary_action_label: __("Mark Completed"),
		primary_action(values) {
			if (requiresAmount && flt(values.resolution_amount) <= 0) {
				frappe.throw(__("Resolution amount must be greater than zero."));
			}
			frappe.call({
				method: "vetedge.services.consultation_cancellation.complete_consultation_cancellation_resolution_manually",
				args: {
					resolution_name: resolutionName,
					completion_note: values.completion_note,
					accounting_reference_doctype: values.accounting_reference_doctype,
					accounting_reference_name: values.accounting_reference_name,
					resolution_amount: values.resolution_amount,
					resolution_date: values.resolution_date,
					external_reference: values.external_reference,
					status_outcome: values.status_outcome,
				},
				freeze: true,
				freeze_message: __("Recording accounting evidence..."),
				callback(result) {
					dialog.hide();
					if (preflightDialog) {
						preflightDialog.hide();
					}
					frappe.msgprint({
						title: __("Accounting Resolution Completed"),
						indicator: "green",
						message: result.message?.message || __("Accounting resolution evidence recorded. Consultation status and submitted accounting documents were unchanged."),
					});
					frm.reload_doc();
				},
			});
		},
	});
	dialog.show();
}

function perform_safe_consultation_cancellation(frm) {
	frappe.call({
		method: "vetedge.services.consultation_cancellation.cancel_consultation_safely",
		args: {
			consultation_name: frm.doc.name,
		},
		freeze: true,
		freeze_message: __("Cancelling consultation..."),
		callback(result) {
			const message = result.message || {};
			const cleaned = message.cleaned_draft_invoices || [];
			const skipped = message.skipped_draft_invoices || [];
			const preservedPatientOutstanding = message.preserved_patient_outstanding_invoices || [];
			const sessions = message.closed_billing_sessions || [];
			const details = [];
			if (cleaned.length) {
				details.push(`${__("Draft invoices cleaned")}: ${cleaned.map(escape_consultation_history_html).join(", ")}`);
			}
			if (skipped.length) {
				details.push(`${__("Draft invoices skipped")}: ${skipped.map((row) => escape_consultation_history_html(row.invoice || row.name || row.reason || "")).filter(Boolean).join(", ")}`);
			}
			if (sessions.length) {
				details.push(`${__("Billing sessions closed")}: ${sessions.map(escape_consultation_history_html).join(", ")}`);
			}
			if (preservedPatientOutstanding.length) {
				details.push(`${__("Other patient invoices preserved")}: ${preservedPatientOutstanding.map(escape_consultation_history_html).join(", ")}`);
			}
			frappe.show_alert({
				message: details.length ? details.join(" | ") : __("Consultation cancelled"),
				indicator: "green",
			});
			frm.reload_doc();
		},
	});
}

function perform_consultation_status_transition(frm, status) {
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
				fieldtype: "Select",
				label: __("Capillary Refill Time"),
				options: "\nLess than 2 seconds\nGreater than 2 seconds",
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
					create_invoice: 0,
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
				frappe.msgprint(__("No vitals found for this consultation."));
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

function add_vaccination_actions(frm) {
	if (!consultationScopeIsLocked(frm)) {
		frm.add_custom_button(__("New Vaccination"), () => {
			show_vaccination_dialog(frm);
		}, __("Clinical"));
	}

	frm.add_custom_button(__("View Vaccinations"), () => {
		show_vaccination_history(frm);
	}, __("Clinical"));
}

function show_vaccination_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("New Vaccination"),
		fields: [
			{ fieldtype: "Link", fieldname: "vaccine", label: __("Vaccine"), options: "Veterinary Vaccine", reqd: 1 },
			{ fieldtype: "Link", fieldname: "billing_item", label: __("Billing Item"), options: "Item", read_only: 1 },
			{
				fieldtype: "Currency",
				fieldname: "rate",
				label: __("Rate"),
				description: __("Edit the Rate before billing to change the vaccination charge."),
			},
			{ fieldtype: "Data", fieldname: "dose", label: __("Dose") },
			{ fieldtype: "Select", fieldname: "route", label: __("Route"), options: "\nOral\nSubcutaneous\nIntramuscular\nIntranasal\nTopical\nOther" },
			{ fieldtype: "Datetime", fieldname: "administered_on", label: __("Administered On"), default: frappe.datetime.now_datetime(), reqd: 1 },
			{ fieldtype: "Date", fieldname: "next_due_date", label: __("Next Due Date") },
			{ fieldtype: "Small Text", fieldname: "notes", label: __("Notes") },
		],
		primary_action_label: __("Save Vaccination"),
		async primary_action(values) {
			if (frm.is_dirty()) {
				await frm.save();
			}
			frappe.call({
				method: "vetedge.services.vaccination.create_vaccination_from_consultation",
				args: {
					consultation: frm.doc.name,
					values,
				},
				freeze: true,
				freeze_message: __("Saving vaccination..."),
				callback(response) {
					const record = response?.message;
					if (!record?.name) {
						return;
					}

					dialog.hide();
					frappe.show_alert({
						message: __("Vaccination recorded"),
						indicator: "green",
					});
					frm.reload_doc();
				},
			});
		},
	});

	dialog.fields_dict.vaccine.df.onchange = async () => {
		const vaccine = dialog.get_value("vaccine");
		if (!vaccine) {
			dialog.set_value("billing_item", null);
			dialog.set_value("rate", null);
			return;
		}
		const response = await frappe.db.get_value("Veterinary Vaccine", vaccine, ["default_item", "default_price"]);
		const defaults = response?.message || {};
		dialog.set_value("billing_item", defaults.default_item || null);
		dialog.set_value("rate", defaults.default_price || 0);
	};

	dialog.show();
}

function formatVaccinationBilling(row) {
	if (!row.linked_invoice) {
		return __("Not billed");
	}

	const parts = [frappe.utils.escape_html(row.linked_invoice)];
	if (row.billing_status) {
		parts.push(frappe.utils.escape_html(row.billing_status));
	}
	if (row.invoice_total != null) {
		parts.push(format_currency(row.invoice_total));
	}
	if (row.invoice_outstanding_amount != null) {
		parts.push(`${__("Outstanding")}: ${format_currency(row.invoice_outstanding_amount)}`);
	}
	return parts.join(" | ");
}

function show_vaccination_history(frm) {
	frappe.call({
		method: "vetedge.services.vaccination.get_consultation_vaccinations",
		args: { consultation: frm.doc.name, limit: 20 },
		freeze: true,
		freeze_message: __("Loading consultation vaccinations..."),
		callback(response) {
			const rows = response?.message || [];
			const html = rows.length
				? `
					<div class="table-responsive">
						<table class="table table-bordered table-sm">
							<thead>
								<tr>
									<th>${__("Date")}</th>
									<th>${__("Vaccine")}</th>
									<th>${__("Practitioner")}</th>
									<th>${__("Branch")}</th>
									<th>${__("Workflow")}</th>
									<th>${__("Next Due")}</th>
									<th>${__("Billing")}</th>
								</tr>
							</thead>
							<tbody>
								${rows
									.map(
										(row) => `
											<tr>
												<td>${frappe.datetime.str_to_user(row.timestamp || row.administered_on || "")}</td>
												<td>
													<b>${frappe.utils.escape_html(row.vaccine || "")}</b>
													${row.dose ? `<br>${__("Dose")}: ${frappe.utils.escape_html(row.dose)}` : ""}
													${row.route ? `<br>${__("Route")}: ${frappe.utils.escape_html(row.route)}` : ""}
												</td>
												<td>${frappe.utils.escape_html(row.administered_by_name || row.administered_by || "")}</td>
												<td>${frappe.utils.escape_html(row.service_branch || "")}</td>
												<td>${frappe.utils.escape_html(row.workflow_status || row.status || "")}</td>
												<td>${row.next_due_date ? `${frappe.datetime.str_to_user(row.next_due_date)}${row.due_state ? ` (${frappe.utils.escape_html(row.due_state)})` : ""}` : __("Not set")}</td>
												<td>${formatVaccinationBilling(row)}</td>
											</tr>`
									)
									.join("")}
							</tbody>
						</table>
					</div>`
				: `<p class="text-muted">${__("No vaccinations linked to this consultation yet.")}</p>`;

			frappe.msgprint({
				title: __("Consultation Vaccinations"),
				message: html,
				indicator: "blue",
				wide: true,
			});
		},
	});
}
