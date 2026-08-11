(function () {
	"use strict";
	if (typeof window === "undefined") return;

	const CLINICAL_WORKSPACE_PATH = "/app/vetedge-clinical-workspace";
	const MEDICAL_HISTORY_PATH = "/app/veterinary-medical-history";
	const RESOURCE_CENTER_PATH = "/app/vetedge-resource-center";
	const MASTER_WORKSPACE_PATH = "/app/vetedge-master-workspace";
	const PRICING_WORKSPACE_PATH = "/app/vetedge-pricing-master-workspace";
	const FRONT_DESK_PATH = "/app/vetedge-front-desk-action-center";
	const SERVICE_WORKSPACE_PATH = "/app/vetedge-service-operations";
	const SETTINGS_PATH = "/app/veterinary-settings-center";

	const RESOURCE_DOCTYPES = Object.freeze({
		"Veterinary Patient": "patients",
		"Veterinary Appointment": "appointments",
	});
	const RESOURCE_PATHS = Object.freeze({
		"/app/veterinary-patient": "patients",
		"/app/veterinary-appointment": "appointments",
	});
	const MASTER_DOCTYPES = Object.freeze({
		"Veterinary Species": "species",
		"Veterinary Breed": "breeds",
		"Veterinary Symptom": "symptoms",
		"Veterinary Diagnosis Category": "diagnosis-categories",
		"Veterinary Diagnosis": "diagnoses",
		"Veterinary Service Type": "service-types",
		"Consultation Type": "consultation-types",
	});
	const MASTER_PATHS = Object.freeze({
		"/app/veterinary-species": "species",
		"/app/veterinary-breed": "breeds",
		"/app/veterinary-symptom": "symptoms",
		"/app/veterinary-diagnosis-category": "diagnosis-categories",
		"/app/veterinary-diagnosis": "diagnoses",
		"/app/veterinary-service-type": "service-types",
		"/app/consultation-type": "consultation-types",
	});
	const PRICING_DOCTYPES = Object.freeze({
		"Veterinary Treatment Item": "treatment-items",
		"Veterinary Treatment Type": "treatment-types",
		"Veterinary Lab Test": "lab-tests",
		"Veterinary Vaccine": "vaccines",
		"Pet Grooming Service": "grooming-services",
	});
	const PRICING_PATHS = Object.freeze({
		"/app/veterinary-treatment-item": "treatment-items",
		"/app/veterinary-treatment-type": "treatment-types",
		"/app/veterinary-lab-test": "lab-tests",
		"/app/veterinary-vaccine": "vaccines",
		"/app/pet-grooming-service": "grooming-services",
	});
	const SERVICE_DOCTYPES = Object.freeze({
		"Pet Boarding Stay": "boarding-stays",
		"Pet Boarding Care Record": "boarding-care-records",
		"Pet Grooming Session": "grooming-sessions",
	});
	const SERVICE_PATHS = Object.freeze({
		"/app/pet-boarding-stay": "boarding-stays",
		"/app/pet-boarding-care-record": "boarding-care-records",
		"/app/pet-grooming-session": "grooming-sessions",
	});
	const SAME_TAB_PAGES = new Set([
		"/app/vetedge",
		RESOURCE_CENTER_PATH,
		MASTER_WORKSPACE_PATH,
		PRICING_WORKSPACE_PATH,
		FRONT_DESK_PATH,
		SERVICE_WORKSPACE_PATH,
		SETTINGS_PATH,
		CLINICAL_WORKSPACE_PATH,
		MEDICAL_HISTORY_PATH,
		"/app/vetedge-executive-dashboard",
		"/app/stock-expiry-monitor",
	]);

	let redirecting = false;
	let adapterScheduled = false;

	function currentRoute() {
		try { return window.frappe?.get_route?.() || []; }
		catch (_error) { return []; }
	}

	function isNewDocumentRoute(name, doctype = "") {
		const value = String(name || "").toLowerCase();
		const slug = String(doctype || "").toLowerCase().replace(/[^a-z0-9]+/g, "-");
		return !value || value === "new" || (slug && value.startsWith(`new-${slug}`));
	}

	function queryTarget(base, params) {
		const query = new URLSearchParams();
		Object.entries(params || {}).forEach(([key, value]) => {
			if (value !== undefined && value !== null && String(value) !== "") query.set(key, String(value));
		});
		const suffix = query.toString();
		return suffix ? `${base}?${suffix}` : base;
	}

	function documentWorkspaceTarget(base, resource, routeType, name, doctype) {
		if (routeType === "List") return queryTarget(base, { resource });
		if (routeType !== "Form") return "";
		if (isNewDocumentRoute(name, doctype)) return queryTarget(base, { resource, new: 1 });
		return queryTarget(base, { resource, name });
	}

	function serviceWorkspaceTarget(resource, routeType, name, doctype) {
		if (routeType === "List") return queryTarget(SERVICE_WORKSPACE_PATH, { resource });
		if (routeType === "Form" && name && !isNewDocumentRoute(name, doctype)) {
			return queryTarget(SERVICE_WORKSPACE_PATH, { resource, name });
		}
		return "";
	}

	function acceptedTargetFromFrappeRoute(route = currentRoute()) {
		const routeType = String(route[0] || "");
		const doctype = String(route[1] || "");
		const name = route[2];

		if (doctype === "Veterinary Consultation") {
			if (routeType === "List") return CLINICAL_WORKSPACE_PATH;
			if (routeType === "Form") {
				return isNewDocumentRoute(name, doctype)
					? `${CLINICAL_WORKSPACE_PATH}?new=1`
					: `${CLINICAL_WORKSPACE_PATH}?consultation=${encodeURIComponent(name)}`;
			}
		}

		if (doctype === "Veterinary Settings" && ["List", "Form"].includes(routeType)) return SETTINGS_PATH;

		// Veterinary Vital Signs remains an explicit Clinical menu destination.
		// Consultation-linked capture is available inside Clinical Workspace, while the
		// standalone DocType remains available for list/audit workflows until its own
		// dedicated EdgeSuite migration is accepted.
		if (doctype === "Veterinary Vital Signs") return "";

		if (SERVICE_DOCTYPES[doctype]) {
			return serviceWorkspaceTarget(SERVICE_DOCTYPES[doctype], routeType, name, doctype);
		}
		if (RESOURCE_DOCTYPES[doctype]) {
			return documentWorkspaceTarget(RESOURCE_CENTER_PATH, RESOURCE_DOCTYPES[doctype], routeType, name, doctype);
		}
		if (MASTER_DOCTYPES[doctype]) {
			return documentWorkspaceTarget(MASTER_WORKSPACE_PATH, MASTER_DOCTYPES[doctype], routeType, name, doctype);
		}
		if (PRICING_DOCTYPES[doctype]) {
			return documentWorkspaceTarget(PRICING_WORKSPACE_PATH, PRICING_DOCTYPES[doctype], routeType, name, doctype);
		}

		if (doctype === "Veterinary Guest Booking Request") {
			if (routeType === "List") return `${FRONT_DESK_PATH}?tab=guest`;
			if (routeType === "Form" && name) return queryTarget(FRONT_DESK_PATH, { tab: "guest", name });
		}
		if (doctype === "Veterinary Missed Appointment") {
			if (routeType === "List") return `${FRONT_DESK_PATH}?tab=missed`;
			if (routeType === "Form" && name) return queryTarget(FRONT_DESK_PATH, { tab: "missed", name });
		}
		return "";
	}

	function redirectAcceptedRoute() {
		if (redirecting) return false;
		const target = acceptedTargetFromFrappeRoute();
		if (!target) return false;
		const current = `${window.location.pathname}${window.location.search}`;
		if (current === target) return false;

		redirecting = true;
		if (navigateAcceptedTarget(target, {
			replace: true,
			onSettled: () => { redirecting = false; },
		})) {
			return true;
		}

		redirecting = false;
		window.location.replace(target);
		return true;
	}

	function normalizeRoute(route) {
		const raw = String(route || "").trim();
		if (!raw) return { raw: "", path: "", search: "" };
		try {
			const url = new URL(raw, window.location.origin);
			return { raw, path: url.pathname.replace(/\/$/, "") || "/", search: url.search || "" };
		} catch (_error) {
			const [path, query = ""] = raw.split("?");
			return { raw, path: path.replace(/\/$/, ""), search: query ? `?${query}` : "" };
		}
	}

	function navigateAcceptedTarget(target, options = {}) {
		try {
			const url = new URL(String(target || "").trim(), window.location.origin);
			const router = window.frappe?.router;
			const isSameOrigin = url.origin === window.location.origin;
			const isDeskRoute = /^\/(app|desk)(\/|$)/.test(url.pathname);
			if (!isSameOrigin || !isDeskRoute || typeof router?.route !== "function") return false;

			const current = `${window.location.pathname}${window.location.search}${window.location.hash}`;
			const next = `${url.pathname}${url.search}${url.hash}`;
			if (current === next) {
				options.onSettled?.();
				return true;
			}

			window.frappe.route_options = {};
			for (const [key, value] of url.searchParams) {
				window.frappe.route_options[key] = value;
			}
			window.frappe.route_hash = url.hash || null;

			const method = options.replace ? "replaceState" : "pushState";
			window.history[method](null, "", next);
			Promise.resolve(router.route())
				.catch((error) => {
					console.error("VetEdge accepted-route navigation failed:", error);
					if (options.replace) window.location.replace(next);
					else window.location.assign(next);
				})
				.finally(() => options.onSettled?.());
			return true;
		} catch (error) {
			if (window.frappe?.boot?.developer_mode) {
				console.warn("[VetEdgeRouteAlignment] Unable to use Desk routing", error);
			}
			return false;
		}
	}

	function pathWorkspaceTarget(path, search = "") {
		if (SAME_TAB_PAGES.has(path)) return `${path}${search}`;
		if (path === "/app/veterinary-settings") return SETTINGS_PATH;
		if (path === "/app/veterinary-appointment-queue") return `${FRONT_DESK_PATH}?tab=queue`;
		if (path === "/app/kennel-availability" || path === "/app/kennel-availability-board") {
			return queryTarget(SERVICE_WORKSPACE_PATH, { resource: "availability" });
		}

		const clinicalBase = "/app/veterinary-consultation";
		if (path === clinicalBase) return CLINICAL_WORKSPACE_PATH;
		if (path.startsWith(`${clinicalBase}/`)) {
			const name = decodeURIComponent(path.slice(clinicalBase.length + 1));
			return isNewDocumentRoute(name, "Veterinary Consultation")
				? `${CLINICAL_WORKSPACE_PATH}?new=1`
				: `${CLINICAL_WORKSPACE_PATH}?consultation=${encodeURIComponent(name)}`;
		}

		for (const [base, resource] of Object.entries(SERVICE_PATHS)) {
			if (path === base) return queryTarget(SERVICE_WORKSPACE_PATH, { resource });
			if (path.startsWith(`${base}/`)) {
				const name = decodeURIComponent(path.slice(base.length + 1));
				if (isNewDocumentRoute(name, base.slice(5))) return "";
				return queryTarget(SERVICE_WORKSPACE_PATH, { resource, name });
			}
		}
		for (const [base, resource] of Object.entries(RESOURCE_PATHS)) {
			if (path === base) return queryTarget(RESOURCE_CENTER_PATH, { resource });
			if (path.startsWith(`${base}/`)) {
				const name = decodeURIComponent(path.slice(base.length + 1));
				return isNewDocumentRoute(name, base.slice(5))
					? queryTarget(RESOURCE_CENTER_PATH, { resource, new: 1 })
					: queryTarget(RESOURCE_CENTER_PATH, { resource, name });
			}
		}
		for (const [base, resource] of Object.entries(MASTER_PATHS)) {
			if (path === base) return queryTarget(MASTER_WORKSPACE_PATH, { resource });
			if (path.startsWith(`${base}/`)) {
				const name = decodeURIComponent(path.slice(base.length + 1));
				return isNewDocumentRoute(name, base.slice(5))
					? queryTarget(MASTER_WORKSPACE_PATH, { resource, new: 1 })
					: queryTarget(MASTER_WORKSPACE_PATH, { resource, name });
			}
		}
		for (const [base, resource] of Object.entries(PRICING_PATHS)) {
			if (path === base) return queryTarget(PRICING_WORKSPACE_PATH, { resource });
			if (path.startsWith(`${base}/`)) {
				const name = decodeURIComponent(path.slice(base.length + 1));
				return isNewDocumentRoute(name, base.slice(5))
					? queryTarget(PRICING_WORKSPACE_PATH, { resource, new: 1 })
					: queryTarget(PRICING_WORKSPACE_PATH, { resource, name });
			}
		}

		const frontDesk = [
			["/app/veterinary-guest-booking-request", "guest"],
			["/app/veterinary-missed-appointment", "missed"],
		];
		for (const [base, tab] of frontDesk) {
			if (path === base) return queryTarget(FRONT_DESK_PATH, { tab });
			if (path.startsWith(`${base}/`)) {
				const name = decodeURIComponent(path.slice(base.length + 1));
				return queryTarget(FRONT_DESK_PATH, { tab, name });
			}
		}
		return "";
	}

	function installNavigationAdapter() {
		const edgeUI = window.EdgeSuiteUI || window.EdgeUI;
		if (!edgeUI?.getAdapter || !edgeUI?.registerAdapter) return false;
		const current = edgeUI.getAdapter("navigation:vetedge") || edgeUI.getAdapter("navigation:veterinary");
		if (!current) return false;
		if (current.__vetedgeAcceptedRouteAlignment) return true;

		const wrapped = {
			...current,
			__vetedgeAcceptedRouteAlignment: true,
			open(route) {
				const normalized = normalizeRoute(route);
				const target = pathWorkspaceTarget(normalized.path, normalized.search);
				if (target) {
					if (navigateAcceptedTarget(target)) return true;
					window.location.assign(target);
					return true;
				}
				return current.open?.(route) === true;
			},
		};
		edgeUI.registerAdapter("navigation:vetedge", wrapped, { replace: true });
		edgeUI.registerAdapter("navigation:veterinary", wrapped, { replace: true });
		return true;
	}

	function scheduleNavigationAdapter() {
		if (adapterScheduled) return;
		adapterScheduled = true;
		window.setTimeout(() => {
			adapterScheduled = false;
			installNavigationAdapter();
		}, 0);
	}

	window.VetEdgeRouteAlignment = Object.assign(window.VetEdgeRouteAlignment || {}, {
		install: redirectAcceptedRoute,
		installNavigationAdapter,
		acceptedTargetFromFrappeRoute,
		pathWorkspaceTarget,
		navigateAcceptedTarget,
	});
	window.VetEdgeClinicalRoute = Object.assign(window.VetEdgeClinicalRoute || {}, {
		install: redirectAcceptedRoute,
		workspacePath: CLINICAL_WORKSPACE_PATH,
	});

	window.frappe?.router?.on?.("change", redirectAcceptedRoute);
	window.frappe?.router?.on?.("change", scheduleNavigationAdapter);
	for (const eventName of ["page-change", "desktop_screen", "sidebar_setup", "toolbar_setup"]) {
		document.addEventListener(eventName, redirectAcceptedRoute);
		document.addEventListener(eventName, scheduleNavigationAdapter);
	}
	window.setTimeout(redirectAcceptedRoute, 100);
	window.setTimeout(scheduleNavigationAdapter, 250);
	window.setTimeout(redirectAcceptedRoute, 500);
	window.setTimeout(scheduleNavigationAdapter, 1000);
})();