frappe.pages.vetedge.on_page_load = function(wrapper) {
	wrapper.page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Veterinary Home'),
		single_column: true
	});
	$('<div class="p-6 text-center text-muted"></div>')
		.text(__('Opening Veterinary Dashboard...'))
		.appendTo(wrapper.page.body);
};

frappe.pages.vetedge.on_page_show = function(wrapper) {
	if (wrapper.vetedge_home_redirecting) return;
	wrapper.vetedge_home_redirecting = true;
	frappe.set_route('vetedge-executive-dashboard');
};
