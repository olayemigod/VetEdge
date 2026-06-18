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
			filters: {
				disabled: 0,
			},
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
			try {
				add_vaccination_actions(frm);
			} catch (error) {
				console.error("Failed to initialize vaccination actions", error);
			}

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

function show_medical_history_dialog(frm) {
	if (!frm.doc.patient) {
		frappe.msgprint(__("Select a patient/animal before viewing medical history."));
		return;
	}

	const dialog = new frappe.ui.Dialog({
		title: __("Veterinary Medical History"),
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
	const treatments = Array.isArray(row.treatment_plan) ? row.treatment_plan : [];
	if (treatments.length) {
		parts.push(`
			<ul class="mb-0 pl-3">
				${treatments
					.map((treatment) => {
						const item = escape_consultation_history_html(treatment.item || treatment.service_type || treatment.treatment_type || __("Treatment"));
						const qty = treatment.qty ? ` ${escape_consultation_history_html(treatment.qty)}` : "";
						const uom = treatment.uom ? ` ${escape_consultation_history_html(treatment.uom)}` : "";
						const notes = treatment.notes ? `<div class="text-muted small">${escape_consultation_history_html(treatment.notes)}</div>` : "";
						return `<li><div>${item}${qty}${uom}</div>${notes}</li>`;
					})
					.join("")}
			</ul>
		`);
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
	const invoices = getConsultationInvoices(frm);

	if (invoices.length) {
		frm.add_custom_button(__("View Invoices"), () => {
			showConsultationInvoicesDialog(invoices);
		}, __("Billing"));
	}

	if (!["Completed", "Cancelled"].includes(frm.doc.status)) {
		frm.add_custom_button(__(frm.doc.linked_invoice ? "Update Invoice" : "Create Invoice"), () => {
			create_consultation_invoice(frm);
		}, __("Billing"));
	}
}

function add_lab_actions(frm) {
	if (["Completed", "Cancelled"].includes(frm.doc.status)) {
		return;
	}

	if (!consultationScopeIsLocked(frm)) {
		frm.add_custom_button(__("New Lab Order"), () => {
			show_lab_order_dialog(frm);
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
							render_lab_order_results(dialog, orders);
						},
					},
					{
						fieldname: "search_text",
						fieldtype: "Data",
						label: __("Search"),
						change() {
							render_lab_order_results(dialog, orders);
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
			render_lab_order_results(dialog, orders);
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
							frappe.set_route("Form", "Veterinary Lab Order", response.message.name);
						},
					});
				},
			});

			dialog.show();
			render_lab_test_picker(dialog, tests, state);
		},
	});
}

function render_lab_order_results(dialog, orders) {
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
		dialog.hide();
		frappe.set_route("Form", "Veterinary Lab Order", $(this).attr("data-name"));
	});
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
				message: result.message.is_draft_update ? __("Invoice updated") : __("Invoice created"),
				indicator: "green",
			});
			frm.reload_doc();
		},
	});
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

function add_vaccination_actions(frm) {
	frm.add_custom_button(__("New Vaccination"), () => {
		show_vaccination_dialog(frm);
	}, __("Clinical"));

	frm.add_custom_button(__("View Vaccinations"), () => {
		show_vaccination_history(frm);
	}, __("Clinical"));
}

function show_vaccination_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("New Vaccination"),
		fields: [
			{ fieldtype: "Link", fieldname: "vaccine", label: __("Vaccine"), options: "Veterinary Vaccine", reqd: 1 },
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
