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
		void populate_billing_defaults(frm);
	},

	refresh(frm) {
		add_workflow_actions(frm);
		set_billing_field_state(frm);
		void populate_billing_defaults(frm);
	},

	patient(frm) {
		if (!frm.doc.patient && frm.doc.linked_consultation) {
			void frm.set_value("linked_consultation", null);
		}
		void resolve_patient_context(frm);
	},

	vaccine(frm) {
		void populate_billing_defaults(frm);
		void populate_next_due_date(frm);
	},

	rate(frm) {
		if (frm.__setting_vaccination_rate) {
			return;
		}
		frm.set_value("rate_manually_edited", frm.doc.rate ? 1 : 0);
		update_vaccination_amount(frm);
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

function set_billing_field_state(frm) {
	const locked = ["Administered", "Cancelled"].includes(frm.doc.status);
	frm.set_df_property("billing_item", "read_only", locked);
	frm.set_df_property("rate", "read_only", locked);
	frm.set_df_property("rate", "description", __("Edit the Rate before billing to change the vaccination charge."));
}

function add_workflow_actions(frm) {
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

	if (["Draft", "Awaiting Payment", "Pending Administration"].includes(frm.doc.status)) {
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

async function populate_billing_defaults(frm) {
	if (!frm.doc.vaccine) {
		return;
	}
	if (frm.doc.billing_item && (frm.doc.rate || frm.doc.rate_manually_edited)) {
		update_vaccination_amount(frm);
		return;
	}

	const response = await frappe.call({
		method: "vetedge.services.vaccination.get_vaccination_billing_defaults",
		args: {
			vaccine: frm.doc.vaccine,
			company: frm.doc.company,
			customer: frm.doc.primary_owner,
			branch: frm.doc.service_branch,
		},
	});
	const defaults = response?.message || {};
	if (!frm.doc.billing_item && defaults.default_item) {
		await frm.set_value("billing_item", defaults.default_item);
	} else if (!frm.doc.billing_item && defaults.billing_item) {
		await frm.set_value("billing_item", defaults.billing_item);
	}
	if (!frm.doc.rate_manually_edited && !frm.doc.rate && defaults.rate != null) {
		frm.__setting_vaccination_rate = true;
		await frm.set_value("rate", defaults.rate);
		frm.__setting_vaccination_rate = false;
	}
	update_vaccination_amount(frm);
}

function update_vaccination_amount(frm) {
	frm.set_value("amount", flt(frm.doc.rate || 0));
}
