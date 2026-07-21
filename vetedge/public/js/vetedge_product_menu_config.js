(function () {
	"use strict";

	if (typeof window === "undefined") return;

	const TECHNICAL_DESCRIPTIONS = new Set(["page", "doctype", "report", "workspace", "link"]);
	const DESCRIPTIONS = Object.freeze({
		"Veterinary Home": "Working branch and daily operations",
		"Executive Dashboard": "Management overview and performance",
		"Clinical Dashboard": "Clinical activity and outcomes",
		"Financial Dashboard": "Revenue, receivables, and collections",
		"Inventory / Dispensary Dashboard": "Dispensary and inventory activity",
		"Lab Dashboard": "Laboratory workload and status",
		"Vaccination Dashboard": "Vaccination activity and due care",
		"Boarding Dashboard": "Boarding activity and occupancy",
		"Grooming Dashboard": "Grooming bookings and performance",
		"Practitioner Performance Dashboard": "Practitioner activity and outcomes",
		"Branch Performance Dashboard": "Branch operations and performance",
		"Appointment Queue": "Today's Veterinary clinic queue",
		Patients: "Patient registration and records",
		Appointments: "Bookings and appointment records",
		"Guest Booking Requests": "Public booking and registration requests",
		"Missed Appointments": "Follow-up and resolution",
		Customer: "Pet Owner and customer accounts",
		"Sales Invoice": "Invoices and customer balances",
		"Payment Entry": "Payments and invoice allocation",
		Consultations: "Clinical consultations and medical history",
		"Medical History": "Longitudinal patient records",
		"Lab Orders": "Requests, results, and review",
		Vaccinations: "Vaccination history and due care",
		Hospitalisations: "Admissions, inpatient care, and discharge",
		Grooming: "Grooming bookings and sessions",
		Boarding: "Boarding bookings and stays",
		Kennels: "Kennels and care locations",
		"Stock Expiry Monitor": "Expiry risk and stock action",
		"Veterinary Settings": "Workflow, billing, branding, and notifications",
		Branches: "Company and operational defaults",
		"Role Bundles": "Role-based Veterinary access",
	});

	function businessDescription(item) {
		const supplied = String(item?.description || item?.subtitle || "").trim();
		if (supplied && !TECHNICAL_DESCRIPTIONS.has(supplied.toLowerCase())) return supplied;
		return DESCRIPTIONS[item?.label] || "Open Veterinary workspace item";
	}

	function normalizeItem(item) {
		const normalized = { ...item, description: businessDescription(item) };
		if (normalized.label === "Veterinary Settings" || normalized.link_to === "Veterinary Settings") {
			normalized.link_type = "Page";
			normalized.link_to = "veterinary-settings-center";
			normalized.route = "/app/veterinary-settings-center";
		}
		return normalized;
	}

	function transformConfig(config) {
		const product = String(config?.product || "").trim().toLowerCase();
		if (!["vetedge", "veterinary"].includes(product)) return config;

		let primaryItem = config.primary_item || config.primaryItem || null;
		const sections = (config.sections || []).map((section) => {
			const items = [];
			(section.items || []).forEach((rawItem) => {
				const item = normalizeItem(rawItem);
				if (item.label === "Veterinary Home" || item.link_to === "vetedge-home") {
					primaryItem = primaryItem || item;
					return;
				}
				items.push(item);
			});
			return { ...section, items };
		}).filter((section) => section.items.length);

		primaryItem = normalizeItem(primaryItem || {
			label: "Veterinary Home",
			icon: "home",
			link_type: "Page",
			link_to: "vetedge-home",
			route: "/app/vetedge-home",
		});

		return {
			...config,
			product: "Veterinary",
			subtitle: config.subtitle || "Veterinary Practice Management",
			primary_item: primaryItem,
			sections,
		};
	}

	function patchSidebarDescriptions() {
		const sidebars = window.frappe?.boot?.workspace_sidebar_item;
		const sidebar = sidebars && (sidebars.vetedge || sidebars.veterinary);
		(sidebar?.items || []).forEach((item) => {
			if (item.type !== "Link") return;
			item.description = businessDescription(item);
			if (item.label === "Veterinary Settings" || item.link_to === "Veterinary Settings") {
				item.link_type = "Page";
				item.link_to = "veterinary-settings-center";
				item.route = "/app/veterinary-settings-center";
			}
		});
	}

	function install() {
		patchSidebarDescriptions();
		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		if (!runtime?.registerProductMenu) return false;
		if (runtime.__vetedgePrimaryMenuContractInstalled) return true;
		const original = runtime.registerProductMenu.bind(runtime);
		runtime.registerProductMenu = (config) => original(transformConfig(config));
		runtime.__vetedgePrimaryMenuContractInstalled = true;
		return true;
	}

	if (!install()) {
		document.addEventListener("DOMContentLoaded", install, { once: true });
		window.setTimeout(install, 100);
		window.setTimeout(install, 500);
	}
})();
