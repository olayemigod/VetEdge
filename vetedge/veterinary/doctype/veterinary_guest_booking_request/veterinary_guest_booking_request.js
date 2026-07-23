frappe.ui.form.on('Veterinary Guest Booking Request', {
	refresh(frm) {
		const query = frm.is_new()
			? 'tab=guest'
			: `tab=guest&name=${encodeURIComponent(frm.doc.name)}`;
		window.location.replace(`/app/vetedge-front-desk-action-center?${query}`);
	}
});
