frappe.pages['veterinary-appointment-queue'].on_page_load = function() {
	window.location.replace('/desk/vetedge-front-desk-queue');
};

frappe.pages['veterinary-appointment-queue'].on_page_show = function() {
	if (window.location.pathname !== '/desk/vetedge-front-desk-queue') {
		window.location.replace('/desk/vetedge-front-desk-queue');
	}
};
