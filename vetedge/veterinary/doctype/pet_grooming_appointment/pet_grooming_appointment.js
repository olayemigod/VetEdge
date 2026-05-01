frappe.ui.form.on("Pet Grooming Appointment", {
	setup(frm) {
		frm.set_query("groomer", () => ({
			query: "vetedge.services.permissions.get_grooming_staff_users",
		}));
	},

	async patient(frm) {
		if (!frm.doc.patient) {
			await frm.set_value("primary_owner", null);
			return;
		}
		const response = await frappe.db.get_value("Veterinary Patient", frm.doc.patient, ["primary_owner", "default_branch"]);
		const patient = response?.message || {};
		await frm.set_value("primary_owner", patient.primary_owner || null);
		if (!frm.doc.service_branch && patient.default_branch) {
			await frm.set_value("service_branch", patient.default_branch);
		}
	},

	refresh(frm) {
		if (frm.is_new()) {
			return;
		}
		toggleTerminalGroomingAppointmentReadOnly(frm);
		add_grooming_appointment_actions(frm);
	},
});

function toggleTerminalGroomingAppointmentReadOnly(frm) {
	const isTerminal = ["Completed", "Cancelled"].includes(frm.doc.status);
	(frm.meta.fields || []).forEach((field) => {
		if (!field.fieldname || field.read_only || field.allow_on_submit) {
			return;
		}
		frm.set_df_property(field.fieldname, "read_only", isTerminal ? 1 : 0);
	});
	if (isTerminal) {
		frm.disable_save();
		return;
	}
	frm.enable_save();
}

function add_grooming_appointment_actions(frm) {
	const statusActions = {
		Scheduled: ["Confirmed", "Cancelled", "No Show"],
		Confirmed: ["Checked In", "In Progress", "Cancelled", "No Show"],
		"Checked In": ["In Progress", "Cancelled"],
		"In Progress": ["Completed", "Cancelled"],
	};
	(statusActions[frm.doc.status] || []).forEach((status) => {
		frm.add_custom_button(__(status), () => transitionGroomingAppointment(frm, status), __("Workflow"));
	});

	if (!["Completed", "Cancelled", "No Show"].includes(frm.doc.status)) {
		frm.add_custom_button(__("Create Grooming Session"), () => {
			frappe.call({
				method: "vetedge.services.grooming.create_grooming_session_from_appointment",
				args: { appointment: frm.doc.name },
				freeze: true,
				freeze_message: __("Creating grooming session..."),
				callback(result) {
					if (result.message?.name) {
						frappe.set_route("Form", "Pet Grooming Session", result.message.name);
					}
				},
			});
		}, __("Workflow"));
	}

	if (frm.doc.linked_invoice) {
		frm.add_custom_button(__("View Invoice"), () => {
			frappe.set_route("Form", "Sales Invoice", frm.doc.linked_invoice);
		}, __("Billing"));
	}
}

function transitionGroomingAppointment(frm, status) {
	frappe.call({
		method: "vetedge.services.grooming.transition_grooming_appointment_status",
		args: { appointment: frm.doc.name, status },
		freeze: true,
		freeze_message: __("Updating grooming appointment..."),
		callback() {
			frm.reload_doc();
		},
	});
}
