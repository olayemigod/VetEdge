(function () {
	"use strict";
	if (window.__vetedgeSidebarQaAlignmentInstalled) return;
	window.__vetedgeSidebarQaAlignmentInstalled = true;

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

	function sync() {
		const path = window.location.pathname.replace(/\/$/, "");
		document.querySelectorAll(".edge-app-shell[data-edge-product='vetedge'], .edge-app-shell[data-edge-product='veterinary']").forEach((shell) => {
			movePlannedTreatmentToReports(shell);
			if (path === "/desk/vetedge-vitals-center" || path === "/app/vetedge-vitals-center") {
				const clinical = section(shell, "Clinical");
				const vitalSigns = itemIn(clinical, "Vital Signs");
				if (clinical && vitalSigns) expandOnly(shell, clinical, vitalSigns);
			}
			if (path === "/desk/vetedge-treatment-plan-report" || path === "/app/vetedge-treatment-plan-report") {
				const reports = section(shell, "Reports");
				const planned = itemIn(reports, "Planned Treatment");
				if (reports && planned) expandOnly(shell, reports, planned);
			}
		});
	}

	document.addEventListener("click", (event) => {
		const item = event.target?.closest?.(".edge-sidebar-item");
		if (!item || itemLabel(item) !== "Planned Treatment") return;
		event.preventDefault();
		event.stopPropagation();
		event.stopImmediatePropagation?.();
		window.location.assign("/desk/vetedge-treatment-plan-report");
	}, true);

	for (const eventName of ["page-change", "desktop_screen", "sidebar_setup", "toolbar_setup"]) document.addEventListener(eventName, () => window.setTimeout(sync, 0));
	const observer = new MutationObserver(() => window.requestAnimationFrame(sync));
	if (document.body) observer.observe(document.body, { childList: true, subtree: true });
	window.addEventListener("popstate", sync);
	window.setTimeout(sync, 0);
	window.setTimeout(sync, 150);
})();