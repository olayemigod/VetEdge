const VETEDGE_FRONT_DESK_CANONICAL_ROUTES = Object.freeze({
	queue: '/desk/vetedge-front-desk-queue',
	guest: '/desk/vetedge-front-desk-guest-bookings',
	missed: '/desk/vetedge-front-desk-missed-appointments',
});

function vetedgeFrontDeskCompatibilityTarget() {
	const params = new URLSearchParams(window.location.search || '');
	const tab = Object.prototype.hasOwnProperty.call(VETEDGE_FRONT_DESK_CANONICAL_ROUTES, params.get('tab'))
		? params.get('tab')
		: 'queue';
	const name = String(params.get('name') || '').trim();
	const target = new URL(VETEDGE_FRONT_DESK_CANONICAL_ROUTES[tab], window.location.origin);
	if (name) target.searchParams.set('name', name);
	return `${target.pathname}${target.search}`;
}

function redirectVetEdgeFrontDeskCompatibilityRoute() {
	const target = vetedgeFrontDeskCompatibilityTarget();
	const current = `${window.location.pathname}${window.location.search}`;
	if (current === target) return;
	window.location.replace(target);
}

frappe.pages['vetedge-front-desk-action-center'].on_page_load = function() {
	redirectVetEdgeFrontDeskCompatibilityRoute();
};

frappe.pages['vetedge-front-desk-action-center'].on_page_show = function() {
	redirectVetEdgeFrontDeskCompatibilityRoute();
};
