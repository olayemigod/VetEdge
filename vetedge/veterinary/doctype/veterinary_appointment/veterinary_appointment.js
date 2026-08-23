frappe.ui.form.on("Veterinary Appointment", {
	setup(frm) {
		frm.set_query("patient", () => ({
			filters: {
				status: ["!=", "Deceased"],
			},
		}));

		frm.set_query("practitioner", () => ({
			query: "vetedge.services.permissions.get_veterinary_doctor_users",
		}));

		frm.set_query("grooming_service", () => ({
			filters: { is_active: 1 },
		}));

		frm.set_query("groomer", () => ({
			query: "vetedge.services.permissions.get_grooming_staff_users",
		}));
	},

	refresh(frm) {
		set_consultation_link_display(frm);

		if (frm.is_new()) {
			return;
		}

		add_reference_actions(frm);
		load_smart_appointment_actions(frm);
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
				if (!frm.doc.branch && patient.default_branch) {
					frm.set_value("branch", patient.default_branch);
				}
			});
	},

	appointment_type(frm) {
		if (is_grooming_appointment(frm)) {
			frm.set_value("practitioner", "");
			frm.set_value("practitioner_name", "");
			return;
		}
		frm.set_value("grooming_service", "");
		frm.set_value("groomer", "");
		frm.set_value("groomer_name", "");
	},

	practitioner(frm) {
		if (!frm.doc.practitioner) {
			frm.set_value("practitioner_name", "");
			return;
		}

		frappe.db.get_value("User", frm.doc.practitioner, "full_name").then((result) => {
			const full_name = result?.message?.full_name;
			frm.set_value("practitioner_name", full_name || frm.doc.practitioner);
		});
	},

	groomer(frm) {
		if (!frm.doc.groomer) {
			frm.set_value("groomer_name", "");
			return;
		}

		frappe.db.get_value("User", frm.doc.groomer, "full_name").then((result) => {
			const full_name = result?.message?.full_name;
			frm.set_value("groomer_name", full_name || frm.doc.groomer);
		});
	},
});

function normalized_appointment_type(frm) {
	return String(frm.doc.appointment_type || "Consultation").trim() || "Consultation";
}

function is_grooming_appointment(frm) {
	return normalized_appointment_type(frm) === "Grooming";
}

function is_consultation_appointment(frm) {
	return ["Consultation", "Follow Up"].includes(normalized_appointment_type(frm));
}

function set_consultation_link_display(frm) {
	const consultation = is_consultation_appointment(frm);
	frm.toggle_display(
		"follow_up_reference",
		consultation && Boolean(frm.doc.is_follow_up || frm.doc.follow_up_reference)
	);
	frm.toggle_display("linked_consultation", consultation && Boolean(frm.doc.linked_consultation));
}

function add_reference_actions(frm) {
	if (!is_consultation_appointment(frm) || !frm.doc.follow_up_reference) {
		return;
	}
	frm.add_custom_button(__("Open Originating Consultation"), () => {
		open_vetedge_route(`/desk/vetedge-clinical-workspace?consultation=${encodeURIComponent(frm.doc.follow_up_reference)}`);
	}, __("Consultation"));
}

async function load_smart_appointment_actions(frm) {
	const appointment = frm.doc.name;
	try {
		const response = await frappe.call({
			method: "vetedge.services.appointment_actions.get_appointment_action_state",
			args: { appointment },
		});
		if (frm.doc.name !== appointment) return;
		const state = response.message || {};
		if (state.message) {
			frm.dashboard.add_comment(__(state.message), "blue", true);
		}
		for (const action of state.actions || []) {
			add_smart_action_button(frm, action);
		}
	} catch (error) {
		frm.dashboard.add_comment(
			__(error?.message || "Appointment actions could not be loaded. Refresh the appointment and try again."),
			"red",
			true
		);
	}
}

function add_smart_action_button(frm, action) {
	if (!action?.key || !action?.label) return;
	const label = __(action.label);
	frm.add_custom_button(label, () => run_smart_appointment_action(frm, action), __("Appointment"));
	if (action.primary) {
		frm.change_custom_button_type(label, __("Appointment"), "primary");
	}
}

async function run_smart_appointment_action(frm, action) {
	if (!action?.key || frm.__vetedge_appointment_action_busy) return;
	frm.__vetedge_appointment_action_busy = true;
	try {
		const response = await frappe.call({
			method: "vetedge.services.appointment_actions.perform_appointment_action",
			args: {
				appointment: frm.doc.name,
				action: action.key,
				expected_modified: frm.doc.modified,
			},
			freeze: Boolean(action.mutates),
			freeze_message: action.mutates ? __(action.label) : undefined,
		});
		const result = response.message || {};
		if (result.message) {
			frappe.show_alert({ message: __(result.message), indicator: "green" });
		}
		if (result.mutated) {
			await frm.reload_doc();
		}
		if (result.open?.route) {
			open_vetedge_route(result.open.route);
		}
	} catch (error) {
		frappe.msgprint({
			title: __("Appointment action unavailable"),
			message: error?.message || __("The appointment action could not be completed."),
			indicator: "red",
		});
	} finally {
		frm.__vetedge_appointment_action_busy = false;
	}
}

function open_vetedge_route(route) {
	if (!route) return;
	const adapter = (window.EdgeSuiteUI || window.EdgeUI)?.getAdapter?.("navigation:vetedge");
	if (adapter?.open?.(route) === true) return;
	window.location.assign(route);
}
