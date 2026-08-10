(function () {
	"use strict";
	if (typeof window === "undefined") return;

	const WORKSPACE_PATH = "/app/vetedge-clinical-workspace";
	let redirecting = false;

	function currentRoute() {
		try { return window.frappe?.get_route?.() || []; }
		catch (_error) { return []; }
	}

	function isNewDocumentRoute(name) {
		const value = String(name || "").toLowerCase();
		return !value || value === "new" || value.startsWith("new-veterinary-consultation");
	}

	function redirectConsultationRoute() {
		if (redirecting || window.location.pathname === WORKSPACE_PATH) return false;
		const route = currentRoute();
		const routeType = String(route[0] || "");
		const doctype = String(route[1] || "");
		if (doctype !== "Veterinary Consultation") return false;
		let target = WORKSPACE_PATH;
		if (routeType === "Form") {
			target += isNewDocumentRoute(route[2])
				? "?new=1"
				: `?consultation=${encodeURIComponent(route[2])}`;
		} else if (routeType !== "List") {
			return false;
		}
		redirecting = true;
		window.location.replace(target);
		return true;
	}

	window.VetEdgeClinicalRoute = Object.assign(window.VetEdgeClinicalRoute || {}, {
		install: redirectConsultationRoute,
		workspacePath: WORKSPACE_PATH,
	});
	window.frappe?.router?.on?.("change", redirectConsultationRoute);
	document.addEventListener("page-change", redirectConsultationRoute);
	window.setTimeout(redirectConsultationRoute, 100);
	window.setTimeout(redirectConsultationRoute, 500);
})();
