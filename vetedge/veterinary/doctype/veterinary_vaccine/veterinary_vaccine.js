frappe.ui.form.on('Veterinary Vaccine', {
	refresh(frm) {
		const query = frm.is_new()
			? 'resource=vaccines&new=1'
			: `resource=vaccines&name=${encodeURIComponent(frm.doc.name)}`;
		window.location.replace(`/app/vetedge-pricing-master-workspace?${query}`);
	}
});
