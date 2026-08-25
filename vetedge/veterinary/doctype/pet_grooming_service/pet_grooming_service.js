frappe.ui.form.on('Pet Grooming Service', {
	refresh(frm) {
		const query = frm.is_new()
			? 'resource=grooming-services&new=1'
			: `resource=grooming-services&name=${encodeURIComponent(frm.doc.name)}`;
		window.location.replace(`/desk/vetedge-pricing-master-workspace?${query}`);
	}
});
