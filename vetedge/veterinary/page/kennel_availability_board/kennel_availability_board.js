frappe.pages['kennel-availability-board'].on_page_load = function(wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Kennel Availability Board'),
		single_column: true,
	});
};

frappe.pages['kennel-availability-board'].on_page_show = function() {
	const target = '/app/vetedge-service-operations?resource=availability';
	const current = `${window.location.pathname}${window.location.search}`;
	if (current !== target) window.location.replace(target);
};
