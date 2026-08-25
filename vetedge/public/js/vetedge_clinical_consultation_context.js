(function () {
	if (window.__vetedgeClinicalConsultationContextInstalled) return;
	window.__vetedgeClinicalConsultationContextInstalled = true;

	const CLOSED = ["Completed", "Cancelled"];

	function openConsultationQuery(frm) {
		if (!frm.doc.patient) return { filters: { name: ["=", ""] } };
		return {
			filters: {
				patient: frm.doc.patient,
				status: ["not in", CLOSED],
			},
		};
	}

	function labHasResultContent(frm) {
		return (frm.doc.lab_tests || []).some((row) =>
			["result_value", "result_text", "result_attachment", "remarks"].some(
				(fieldname) => ![undefined, null, ""].includes(row[fieldname]),
			),
		);
	}

	function configureLabContext(frm) {
		frm.set_query("consultation", () => openConsultationQuery(frm));
		const assignable =
			!frm.doc.consultation &&
			["Draft", "Ordered"].includes(frm.doc.status || "Draft") &&
			!frm.doc.linked_invoice &&
			!labHasResultContent(frm);
		frm.set_df_property("consultation", "read_only", assignable ? 0 : 1);
		frm.set_df_property("patient", "read_only", assignable ? 0 : 1);
		frm.set_df_property(
			"consultation",
			"description",
			__("Optional. Only open consultations for this patient are available. The link is locked after assignment, billing, or clinical processing starts."),
		);
	}

	function configureVaccinationContext(frm) {
		frm.set_query("linked_consultation", () => openConsultationQuery(frm));
		const assignable =
			!frm.doc.linked_consultation &&
			(frm.doc.status || "Draft") === "Draft" &&
			!frm.doc.linked_invoice &&
			!frm.doc.stock_entry_reference;
		frm.set_df_property("linked_consultation", "read_only", assignable ? 0 : 1);
		frm.set_df_property("patient", "read_only", assignable ? 0 : 1);
		frm.set_df_property(
			"linked_consultation",
			"description",
			__("Optional. Only open consultations for this patient are available. The link is locked after assignment, billing, or administration starts."),
		);
	}

	frappe.ui.form.on("Veterinary Lab Order", {
		setup: configureLabContext,
		refresh: configureLabContext,
		patient: configureLabContext,
		status: configureLabContext,
		consultation: configureLabContext,
		linked_invoice: configureLabContext,
	});

	frappe.ui.form.on("Veterinary Vaccination Record", {
		setup: configureVaccinationContext,
		refresh: configureVaccinationContext,
		patient: configureVaccinationContext,
		status: configureVaccinationContext,
		linked_consultation: configureVaccinationContext,
		linked_invoice: configureVaccinationContext,
		stock_entry_reference: configureVaccinationContext,
	});
})();