(() => {
	const PRACTITIONER_QUERY = "vetedge.services.hospitalisation_form_integrity.search_hospitalisation_practitioners";
	const PRACTITIONER_CHECK = "vetedge.services.hospitalisation_form_integrity.is_hospitalisation_practitioner_allowed";

	function applyHospitalisationPractitionerQuery(frm) {
		if (!frm?.set_query) return;
		frm.set_query("attending_veterinarian", () => ({
			query: PRACTITIONER_QUERY,
			filters: { branch: frm.doc.service_branch || "" },
		}));
	}

	function queueHospitalisationPractitionerQuery(frm) {
		window.setTimeout(() => applyHospitalisationPractitionerQuery(frm), 0);
	}

	async function clearInvalidHospitalisationPractitioner(frm) {
		queueHospitalisationPractitionerQuery(frm);
		const practitioner = frm.doc.attending_veterinarian;
		if (!practitioner || !frm.doc.service_branch || !window.frappe?.call) return;
		try {
			const response = await frappe.call({
				method: PRACTITIONER_CHECK,
				args: {
					branch: frm.doc.service_branch,
					practitioner,
				},
			});
			if (response?.message === false && frm.doc.attending_veterinarian === practitioner) {
				await frm.set_value("attending_veterinarian", null);
				frappe.show_alert({
					message: __("Attending Veterinarian was cleared because the user is not assigned to the selected Branch."),
					indicator: "orange",
				});
			}
		} catch (_error) {
			// Backend validation remains authoritative. Avoid masking the form with a
			// client-only failure if the validation request cannot complete.
		}
	}

	frappe.ui.form.on("Veterinary Hospitalisation", {
		setup(frm) {
			queueHospitalisationPractitionerQuery(frm);
		},
		onload(frm) {
			queueHospitalisationPractitionerQuery(frm);
		},
		refresh(frm) {
			queueHospitalisationPractitionerQuery(frm);
		},
		service_branch(frm) {
			void clearInvalidHospitalisationPractitioner(frm);
		},
	});
})();
