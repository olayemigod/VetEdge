function redirectLegacyKennelAvailability() {
	const target = '/desk/vetedge-service-operations?resource=availability';
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

frappe.pages['kennel-availability'].on_page_load = function(wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Kennel Availability'),
		single_column: true,
	});
};

frappe.pages['kennel-availability'].on_page_show = function() {
	redirectLegacyKennelAvailability();
};
