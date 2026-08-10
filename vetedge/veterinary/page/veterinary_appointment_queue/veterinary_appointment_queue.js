frappe.pages['veterinary-appointment-queue'].on_page_load = function() {
	window.location.replace('/app/vetedge-front-desk-action-center?tab=queue');
};

frappe.pages['veterinary-appointment-queue'].on_page_show = function() {
	if (window.location.pathname !== '/app/vetedge-front-desk-action-center') {
		window.location.replace('/app/vetedge-front-desk-action-center?tab=queue');
	}
};
