frappe.ui.form.on('Veterinary Missed Appointment', {
	refresh(frm) {
		const query = frm.is_new()
			? 'tab=missed'
			: `tab=missed&name=${encodeURIComponent(frm.doc.name)}`;
		window.location.replace(`/desk/vetedge-front-desk-action-center?${query}`);
	}
});
