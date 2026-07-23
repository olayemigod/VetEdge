(function () {
	const WORKSPACE_PATH = "/app/vetedge-clinical-workspace";

	function isWorkspaceRoute() {
		return window.location.pathname === WORKSPACE_PATH;
	}

	function redirectConsultation(frm) {
		if (!frm || frm.__vetedge_clinical_workspace_redirecting || isWorkspaceRoute()) return;
		frm.__vetedge_clinical_workspace_redirecting = true;
		const params = new URLSearchParams({ tab: "consultations" });
		if (frm.is_new?.()) params.set("new", "1");
		else if (frm.doc?.name) params.set("name", frm.doc.name);
		window.location.replace(`${WORKSPACE_PATH}?${params.toString()}`);
	}

	frappe.ui.form.on("Veterinary Consultation", {
		onload(frm) { redirectConsultation(frm); },
		refresh(frm) { redirectConsultation(frm); },
	});
})();
