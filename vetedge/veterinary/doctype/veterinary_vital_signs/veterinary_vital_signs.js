function openEdgeSuiteVitalSigns(frm) {
	if (!frm?.doc?.name || frm.is_new?.()) return;
	window.location.replace(`/desk/vetedge-vitals-center?name=${encodeURIComponent(frm.doc.name)}`);
}

frappe.ui.form.on('Veterinary Vital Signs', {
	onload(frm) {
		openEdgeSuiteVitalSigns(frm);
	},
	refresh(frm) {
		openEdgeSuiteVitalSigns(frm);
	}
});
