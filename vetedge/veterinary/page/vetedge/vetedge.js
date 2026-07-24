function vetedgeHomeHasAnyRole(roles) {
	const current = new Set(window.frappe?.user_roles || []);
	return roles.some((role) => current.has(role));
}

function resolveVetEdgeHomeRoute() {
	if (vetedgeHomeHasAnyRole(['System Manager', 'VetEdge Administrator'])) {
		return 'vetedge-executive-dashboard';
	}
	if (vetedgeHomeHasAnyRole(['VetEdge Doctor', 'Veterinary Nurse', 'VetEdge Nurse'])) {
		return 'vetedge-clinical-workspace';
	}
	if (vetedgeHomeHasAnyRole(['VetEdge Front Desk', 'Branch Manager', 'VetEdge Branch Manager'])) {
		return 'vetedge-front-desk-action-center';
	}
	if (vetedgeHomeHasAnyRole(['Dispensary User'])) {
		return 'stock-expiry-monitor';
	}
	return 'vetedge-clinical-workspace';
}

frappe.pages.vetedge.on_page_load = function(wrapper) {
	wrapper.page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Veterinary Home'),
		single_column: true
	});
	$('<div class="p-6 text-center text-muted"></div>')
		.text(__('Opening your Veterinary workspace...'))
		.appendTo(wrapper.page.body);
};

frappe.pages.vetedge.on_page_show = function(wrapper) {
	if (wrapper.vetedge_home_redirecting) return;
	wrapper.vetedge_home_redirecting = true;
	frappe.set_route(resolveVetEdgeHomeRoute());
};
