frappe.pages['vetedge-front-desk-queue'].on_page_load = function(wrapper) {
	wrapper.page = frappe.ui.make_app_page({ parent: wrapper, title: __('Appointment Queue'), single_column: true });
};

frappe.pages['vetedge-front-desk-queue'].on_page_show = function(wrapper) {
	frappe.require('/assets/vetedge/js/vetedge_front_desk_page_host.js', () => {
		window.VetEdgeFrontDeskPageHost?.mount(wrapper, { fixedTab: 'queue', title: 'Appointment Queue' });
	});
};
