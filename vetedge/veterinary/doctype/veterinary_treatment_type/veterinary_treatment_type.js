frappe.ui.form.on('Veterinary Treatment Type', {
	refresh(frm) {
		const query = frm.is_new()
			? 'resource=treatment-types&new=1'
			: `resource=treatment-types&name=${encodeURIComponent(frm.doc.name)}`;
		window.location.replace(`/desk/vetedge-pricing-master-workspace?${query}`);
	}
});
