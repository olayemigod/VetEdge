function redirectLegacyAppointmentQueue() {
	const target = '/desk/vetedge-front-desk-action-center?tab=queue';
	const current = `${window.location.pathname}${window.location.search}`;
	if (current === target) return;

	try {
		if (typeof frappe?.router?.route === 'function' && window.history?.replaceState) {
			window.history.replaceState(null, '', target);
			Promise.resolve(frappe.router.route()).catch(() => window.location.replace(target));
			return;
		}
	} catch (_error) {
		// Fall back to a normal navigation when Desk routing is unavailable.
	}
	window.location.replace(target);
}

frappe.pages['veterinary-appointment-queue'].on_page_load = function(wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Appointment Queue'),
		single_column: true,
	});
};

frappe.pages['veterinary-appointment-queue'].on_page_show = function() {
	redirectLegacyAppointmentQueue();
};
