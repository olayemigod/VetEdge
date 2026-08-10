frappe.ui.form.on('Veterinary Treatment Item', {
	refresh(frm) {
		const query = frm.is_new()
			? 'resource=treatment-items&new=1'
			: `resource=treatment-items&name=${encodeURIComponent(frm.doc.name)}`;
		window.location.replace(`/app/vetedge-pricing-master-workspace?${query}`);
	}
});
