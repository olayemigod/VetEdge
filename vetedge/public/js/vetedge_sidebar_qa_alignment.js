(function () {
	"use strict";
	if (window.__vetedgeSidebarQaAlignmentInstalled) return;
	window.__vetedgeSidebarQaAlignmentInstalled = true;

	const MIGRATED_REPORTS = Object.freeze({
		"Consultation Register": "Consultation Register",
		"Patient Register": "Patient Register",
		"Owner Register": "Owner Register",
		"Lab Order Report": "Lab Order Report",
		"Laboratory Report": "Lab Order Report",
		"Vaccination Report": "Vaccination Report",
		"Practitioner Performance Report": "Practitioner Performance Report",
		"Branch Performance Report": "Branch Performance Report",
	});
	const CARE_LOCATION_DOCTYPE = "Veterinary Care Location";
	const CARE_LOCATION_ROUTE = "/desk/vetedge-care-locations";
	const BRANCH_ACCESS_ROUTES = Object.freeze({
		"Branch User Assignment": "/desk/vetedge-branch-access?resource=user-assignments",
		"Branch Practitioner Assignment": "/desk/vetedge-branch-access?resource=practitioner-assignments",
	});
	const SAME_TAB_PRODUCT_PAGES = Object.freeze({
		"Training Centre": "/desk/veterinary-training-centre",
		"Settings": "/desk/veterinary-settings-center",
	});

	function normalizeDeskPath(pathname) {
		let path = String(pathname || "").replace(/\/$/, "") || "/";
		if (path === "/app" || path.startsWith("/app/")) path = `/desk${path.slice(4)}`;
		return path;
	}

	function slug(value) {
		return String(value || "")
			.trim()
			.toLowerCase()
			.replace(/[^a-z0-9]+/g, "-")
			.replace(/^-|-$/g, "");
	}

	function sectionLabel(section) {
		const toggle = section?.querySelector?.(".edge-sidebar__section-toggle");
		return String(toggle?.textContent || "").replace(/[▾▸]/g, "").trim();
	}

	function itemLabel(item) {
		return String(item?.querySelector?.(".edge-sidebar-item__label")?.textContent || item?.textContent || "").trim();
	}

	function section(shell, label) {
		return [...shell.querySelectorAll(".edge-sidebar__section")].find((candidate) => sectionLabel(candidate) === label) || null;
	}

	function itemIn(sectionNode, label) {
		return [...(sectionNode?.querySelectorAll?.(".edge-sidebar-item") || [])].find((candidate) => itemLabel(candidate) === label) || null;
	}

	function expandOnly(shell, activeSection, activeItem) {
		if (!activeSection || !activeItem) return;
		shell.querySelectorAll(".edge-sidebar-item").forEach((item) => {
			const active = item === activeItem;
			item.classList.toggle("active", active);
			if (active) item.setAttribute("aria-current", "page");
			else item.removeAttribute("aria-current");
		});
		shell.querySelectorAll(".edge-sidebar__section").forEach((candidate) => {
			const toggle = candidate.querySelector(".edge-sidebar__section-toggle");
			if (!toggle) return;
			const shouldOpen = candidate === activeSection;
			const isOpen = toggle.getAttribute("aria-expanded") === "true";
			if (shouldOpen !== isOpen) toggle.click();
		});
	}

	function movePlannedTreatmentToReports(shell) {
		const clinical = section(shell, "Clinical");
		const reports = section(shell, "Reports");
		if (!clinical || !reports) return;
		const planned = itemIn(clinical, "Planned Treatment") || itemIn(reports, "Planned Treatment");
		if (!planned) return;
		const reportPeer = itemIn(reports, "Consultation Register");
		const targetParent = reportPeer?.parentElement || reports.querySelector(".edge-sidebar__section-items, .edge-sidebar__items") || reports;
		if (planned.parentElement !== targetParent) targetParent.appendChild(planned);
		planned.dataset.vetedgeTreatmentReport = "1";
	}

	function sourceRoute() {
		const path = normalizeDeskPath(window.location.pathname);
		if (path.startsWith("/desk/query-report/") || path === "/desk/vetedge-report-center") return "/desk/vetedge";
		return `${path}${window.location.search || ""}`;
	}

	function reportCenterTarget(reportName, source = sourceRoute(), preserveSearch = false) {
		const params = preserveSearch ? new URLSearchParams(window.location.search || "") : new URLSearchParams();
		params.set("report", reportName);
		params.set("source", source || "/desk/vetedge");
		return `/desk/vetedge-report-center?${params.toString()}`;
	}

	function sameTab(target, { replace = false } = {}) {
		if (!target) return false;
		const url = new URL(target, window.location.origin);
		if (url.origin !== window.location.origin) return false;
		const next = `${url.pathname}${url.search}${url.hash}`;
		const current = `${window.location.pathname}${window.location.search}${window.location.hash}`;
		if (current === next) return true;
		if (window.history && typeof frappe?.router?.route === "function") {
			window.history[replace ? "replaceState" : "pushState"](window.history.state, "", next);
			Promise.resolve(frappe.router.route()).catch(() => {
				if (replace) window.location.replace(next);
				else window.location.assign(next);
			});
			return true;
		}
		if (replace) window.location.replace(next);
		else window.location.assign(next);
		return true;
	}

	function reportFromNativePath(path) {
		const match = normalizeDeskPath(path).match(/^\/desk\/query-report\/(.+)$/);
		if (!match) return "";
		let name = "";
		try { name = decodeURIComponent(match[1]); } catch (_error) { name = match[1]; }
		return MIGRATED_REPORTS[name] ? name : "";
	}

	function careLocationTargetFromNativePath(path) {
		const normalized = normalizeDeskPath(path);
		const base = "/desk/veterinary-care-location";
		if (normalized === base) return CARE_LOCATION_ROUTE;
		if (!normalized.startsWith(`${base}/`)) return "";
		let name = normalized.slice(base.length + 1);
		try { name = decodeURIComponent(name); } catch (_error) { /* keep route text */ }
		if (!name || name === "new" || name.toLowerCase().startsWith("new-veterinary-care-location")) return `${CARE_LOCATION_ROUTE}?new=1`;
		return `${CARE_LOCATION_ROUTE}?name=${encodeURIComponent(name)}`;
	}

	function branchAccessTargetFromNativePath(path) {
		const normalized = normalizeDeskPath(path);
		for (const [doctype, target] of Object.entries(BRANCH_ACCESS_ROUTES)) {
			const base = `/desk/${slug(doctype)}`;
			if (normalized === base) return target;
			if (!normalized.startsWith(`${base}/`)) continue;
			let name = normalized.slice(base.length + 1);
			try { name = decodeURIComponent(name); } catch (_error) { /* keep route text */ }
			if (!name || name === "new" || name.toLowerCase().startsWith(`new-${slug(doctype)}`)) return `${target}&new=1`;
			return `${target}&name=${encodeURIComponent(name)}`;
		}
		return "";
	}

	function migratedTargetFromRoute(route) {
		const raw = String(route || "").trim();
		if (!raw) return "";
		const url = new URL(raw, window.location.origin);
		const report = reportFromNativePath(url.pathname);
		if (report) return reportCenterTarget(report, sourceRoute());
		const care = careLocationTargetFromNativePath(url.pathname);
		if (care) return care;
		const branchAccess = branchAccessTargetFromNativePath(url.pathname);
		if (branchAccess) return branchAccess;
		return "";
	}

	function redirectCurrentLegacyRoute() {
		const path = window.location.pathname;
		const report = reportFromNativePath(path);
		if (report) {
			sameTab(reportCenterTarget(report, "/desk/vetedge", true), { replace: true });
			return true;
		}
		for (const target of [careLocationTargetFromNativePath(path), branchAccessTargetFromNativePath(path)]) {
			if (!target) continue;
			const url = new URL(target, window.location.origin);
			for (const [key, value] of new URLSearchParams(window.location.search || "")) {
				if (!url.searchParams.has(key)) url.searchParams.set(key, value);
			}
			sameTab(`${url.pathname}${url.search}`, { replace: true });
			return true;
		}
		return false;
	}

	function navigationCandidate(event) {
		return event.target?.closest?.([
			".edge-sidebar-item",
			".vetedge-product-menu-link",
			".edge-product-menu-item",
			".edge-product-menu__item",
			"[data-edge-product-menu] button",
			"[data-edge-product-menu] a",
			"[class*='product-menu'] button",
			"[class*='product-menu'] a",
			"[role='menuitem']",
		].join(", ")) || null;
	}

	function explicitTarget(candidate) {
		return String(candidate?.dataset?.linkTo || candidate?.getAttribute?.("data-link-to") || candidate?.getAttribute?.("href") || "").trim();
	}

	function reportNameFromCandidate(candidate) {
		const explicit = explicitTarget(candidate);
		if (MIGRATED_REPORTS[explicit]) return explicit;
		const text = itemLabel(candidate);
		for (const reportName of Object.keys(MIGRATED_REPORTS)) {
			if (text === reportName || text.startsWith(`${reportName}\n`) || text.includes(reportName)) return reportName;
		}
		return "";
	}

	function isCareLocationCandidate(candidate) {
		const explicit = explicitTarget(candidate);
		if (explicit === CARE_LOCATION_DOCTYPE || explicit === "vetedge-care-locations" || explicit.includes("veterinary-care-location")) return true;
		const text = itemLabel(candidate);
		return text === "Care Locations" || text.startsWith("Care Locations\n") || text.includes("Care Locations");
	}

	function branchAccessCandidateTarget(candidate) {
		const explicit = explicitTarget(candidate);
		const text = itemLabel(candidate);
		for (const [doctype, target] of Object.entries(BRANCH_ACCESS_ROUTES)) {
			if (explicit === doctype || explicit.includes(slug(doctype)) || text === doctype || text.includes(doctype)) return target;
		}
		return "";
	}

	function sameTabProductPageTarget(candidate) {
		const explicit = explicitTarget(candidate);
		const text = itemLabel(candidate);
		for (const [label, target] of Object.entries(SAME_TAB_PRODUCT_PAGES)) {
			if (text === label || text.includes(label)) return target;
			const targetPath = normalizeDeskPath(target);
			if (explicit && (normalizeDeskPath(explicit) === targetPath || explicit.includes(targetPath.split("/").pop()))) return target;
		}
		return "";
	}

	function focusForCurrentRoute() {
		const path = normalizeDeskPath(window.location.pathname);
		const params = new URLSearchParams(window.location.search || "");
		if (path === "/desk/vetedge-report-center") {
			const report = params.get("report") || "";
			const label = MIGRATED_REPORTS[report] || report;
			if (label) return { section: "Reports", label };
		}
		if (path === CARE_LOCATION_ROUTE) return { section: "Configuration", label: "Care Locations" };
		if (path === "/desk/vetedge-branch-access") {
			const resource = params.get("resource") || "user-assignments";
			return {
				section: "Configuration",
				label: resource === "practitioner-assignments" ? "Branch Practitioner Assignment" : "Branch User Assignment",
			};
		}
		if (path === "/desk/veterinary-settings-center") return { section: "Configuration", label: "Settings" };
		if (path === "/desk/veterinary-training-centre") return { section: "Help & Training", label: "Training Centre" };
		if (path === "/desk/vetedge-vitals-center") return { section: "Clinical", label: "Vital Signs" };
		if (path === "/desk/vetedge-treatment-plan-report") return { section: "Reports", label: "Planned Treatment" };
		return null;
	}

	function sync() {
		redirectCurrentLegacyRoute();
		const focus = focusForCurrentRoute();
		document.querySelectorAll(".edge-app-shell[data-edge-product='vetedge'], .edge-app-shell[data-edge-product='veterinary']").forEach((shell) => {
			movePlannedTreatmentToReports(shell);
			if (!focus) return;
			const activeSection = section(shell, focus.section);
			const activeItem = itemIn(activeSection, focus.label);
			if (activeSection && activeItem) expandOnly(shell, activeSection, activeItem);
		});
	}

	document.addEventListener("click", (event) => {
		const candidate = navigationCandidate(event);
		if (!candidate) return;

		if (candidate.matches?.(".edge-sidebar-item") && itemLabel(candidate) === "Planned Treatment") {
			event.preventDefault();
			event.stopPropagation();
			event.stopImmediatePropagation?.();
			sameTab("/desk/vetedge-treatment-plan-report");
			return;
		}

		const reportName = reportNameFromCandidate(candidate);
		if (reportName) {
			event.preventDefault();
			event.stopPropagation();
			event.stopImmediatePropagation?.();
			sameTab(reportCenterTarget(reportName));
			return;
		}

		if (isCareLocationCandidate(candidate)) {
			event.preventDefault();
			event.stopPropagation();
			event.stopImmediatePropagation?.();
			sameTab(CARE_LOCATION_ROUTE);
			return;
		}

		const branchAccessTarget = branchAccessCandidateTarget(candidate);
		if (branchAccessTarget) {
			event.preventDefault();
			event.stopPropagation();
			event.stopImmediatePropagation?.();
			sameTab(branchAccessTarget);
			return;
		}

		const productPageTarget = sameTabProductPageTarget(candidate);
		if (productPageTarget) {
			event.preventDefault();
			event.stopPropagation();
			event.stopImmediatePropagation?.();
			sameTab(productPageTarget);
		}
	}, true);

	window.VetEdgeNavigationCoverage = Object.freeze({
		migratedReports: MIGRATED_REPORTS,
		careLocationRoute: CARE_LOCATION_ROUTE,
		branchAccessRoutes: BRANCH_ACCESS_ROUTES,
		sameTabProductPages: SAME_TAB_PRODUCT_PAGES,
		resolveMigratedRoute: migratedTargetFromRoute,
		navigateMigratedRoute(route) {
			const target = migratedTargetFromRoute(route);
			return target ? sameTab(target) : false;
		},
		sync,
	});

	for (const eventName of ["page-change", "desktop_screen", "sidebar_setup", "toolbar_setup"]) {
		document.addEventListener(eventName, () => window.setTimeout(sync, 0));
	}
	const observer = new MutationObserver(() => window.requestAnimationFrame(sync));
	if (document.body) observer.observe(document.body, { childList: true, subtree: true });
	window.addEventListener("popstate", sync);
	window.setTimeout(sync, 0);
	window.setTimeout(sync, 150);
})();
