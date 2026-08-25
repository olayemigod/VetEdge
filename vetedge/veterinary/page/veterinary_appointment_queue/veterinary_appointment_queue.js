frappe.pages['veterinary-appointment-queue'].on_page_load = function() {
	window.location.replace('/desk/vetedge-front-desk-action-center?tab=queue');
};

frappe.pages['veterinary-appointment-queue'].on_page_show = function() {
	if (window.location.pathname !== '/desk/vetedge-front-desk-action-center') {
		window.location.replace('/desk/vetedge-front-desk-action-center?tab=queue');
	}
};
