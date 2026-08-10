frappe.ui.form.on('Veterinary Lab Test', {
	refresh(frm) {
		const query = frm.is_new()
			? 'resource=lab-tests&new=1'
			: `resource=lab-tests&name=${encodeURIComponent(frm.doc.name)}`;
		window.location.replace(`/app/vetedge-pricing-master-workspace?${query}`);
	}
});
