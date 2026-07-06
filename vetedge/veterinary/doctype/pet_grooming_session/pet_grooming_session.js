frappe.ui.form.on("Pet Grooming Session", {
	setup(frm) {
		frm.set_query("groomer", () => ({
			query: "vetedge.services.permissions.get_grooming_staff_users",
		}));

		frm.set_query("appointment", () => ({
			filters: frm.doc.patient
				? {
					patient: frm.doc.patient,
					status: ["not in", ["Completed", "Cancelled", "No Show"]],
				}
				: { name: ["=", ""] },
		}));
	},

	async patient(frm) {
		if (!frm.doc.patient && frm.doc.appointment) {
			await frm.set_value("appointment", null);
		}
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
		toggleTerminalGroomingSessionReadOnly(frm);
		addGroomingSessionActions(frm);
	},
});

function toggleTerminalGroomingSessionReadOnly(frm) {
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

function addGroomingSessionActions(frm) {
	frm.add_custom_button(__("Billing / Payment"), () => {
		if (window.vetedgeBillingModal?.open) {
			window.vetedgeBillingModal.open(frm);
			return;
		}
		frappe.msgprint(__("Billing modal helper is not available. Please refresh the page."));
	}, __("Billing"));

	if (["Draft", "Awaiting Payment", "Pending Grooming"].includes(frm.doc.status)) {
		frm.add_custom_button(__("Start Grooming"), () => transitionGroomingSession(frm, "In Progress"), __("Workflow"));
	}
	if (frm.doc.status === "In Progress") {
		frm.add_custom_button(__("Complete Grooming"), () => transitionGroomingSession(frm, "Completed"), __("Workflow"));
	}
	if (!["Completed", "Cancelled"].includes(frm.doc.status)) {
		frm.add_custom_button(__("Cancel Session"), () => transitionGroomingSession(frm, "Cancelled"), __("Workflow"));
	}

}

function transitionGroomingSession(frm, status) {
	frappe.call({
		method: "vetedge.services.grooming.transition_grooming_session_status",
		args: { session: frm.doc.name, status },
		freeze: true,
		freeze_message: __("Updating grooming session..."),
		callback() {
			frm.reload_doc();
		},
	});
}
