frappe.ui.form.on("Veterinary Vaccination Record", {
	setup(frm) {
		frm.set_query("administered_by", () => ({
			query: "vetedge.services.permissions.get_vaccination_staff_users",
		}));

		frm.set_query("linked_consultation", () => ({
			filters: frm.doc.patient
				? {
					patient: frm.doc.patient,
					status: ["not in", ["Completed", "Cancelled"]],
				}
				: { name: ["=", ""] },
		}));
	},

	onload(frm) {
		frm.__next_due_date_manually_set = false;
		frm.__setting_vaccination_due_date = false;
	},

	refresh(frm) {
		add_workflow_actions(frm);
	},

	patient(frm) {
		if (!frm.doc.patient && frm.doc.linked_consultation) {
			void frm.set_value("linked_consultation", null);
		}
		void resolve_patient_context(frm);
	},

	vaccine(frm) {
		void populate_next_due_date(frm);
	},

	administered_on(frm) {
		void populate_next_due_date(frm);
	},

	next_due_date(frm) {
		if (!frm.__setting_vaccination_due_date) {
			frm.__next_due_date_manually_set = Boolean(frm.doc.next_due_date);
		}
	},
});

function add_workflow_actions(frm) {
	if (frm.is_new() || frm.doc.status === "Cancelled") {
		return;
	}

	if (["Draft", "Awaiting Payment", "Pending Administration"].includes(frm.doc.status)) {
		frm.add_custom_button(__("Billing / Payment"), () => {
			if (window.vetedgeBillingModal?.open) {
				window.vetedgeBillingModal.open(frm);
				return;
			}
			frappe.msgprint(__("Billing modal helper is not available. Please refresh the page."));
		}, __("Billing"));

		frm.add_custom_button(__("Administer Vaccination"), () => {
			frappe.call({
				method: "vetedge.services.vaccination.administer_vaccination",
				args: { record: frm.doc.name },
				freeze: true,
				freeze_message: __("Administering vaccination..."),
				callback() {
					frm.reload_doc();
				},
			});
		}, __("Workflow"));
	}

	if (frm.doc.linked_invoice) {
		frm.add_custom_button(__("View Invoice"), () => {
			frappe.set_route("Form", "Sales Invoice", frm.doc.linked_invoice);
		}, __("Workflow"));
	}
}

async function resolve_patient_context(frm) {
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
}

async function populate_next_due_date(frm) {
	if (!frm.doc.vaccine || !frm.doc.administered_on) {
		return;
	}

	if (frm.__next_due_date_manually_set && frm.doc.next_due_date) {
		return;
	}

	const response = await frappe.db.get_value(
		"Veterinary Vaccine",
		frm.doc.vaccine,
		["default_next_due_days", "default_validity_days"]
	);
	const defaults = response?.message || {};
	const days = Number(defaults.default_next_due_days || defaults.default_validity_days || 0);
	if (!days) {
		return;
	}

	const administeredDate = String(frm.doc.administered_on).split(" ")[0];
	frm.__setting_vaccination_due_date = true;
	await frm.set_value("next_due_date", frappe.datetime.add_days(administeredDate, days));
	frm.__setting_vaccination_due_date = false;
	frm.__next_due_date_manually_set = false;
}
