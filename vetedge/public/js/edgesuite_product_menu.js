// vetedge/public/js/edgesuite_product_menu.js

(function () {
	if (typeof window === 'undefined') return;

	function register() {
		if (!window.EdgeUI || !window.EdgeUI.registerProductMenu) {
			// If EdgeUI is not loaded yet, retry shortly
			setTimeout(register, 100);
			return;
		}

		window.EdgeUI.registerProductMenu({
			product: "VetEdge",
			sections: [
				{
					label: "Product",
					items: [
						{
							label: "Veterinary Settings",
							link_type: "DocType",
							link_to: "Veterinary Settings",
							display_depends_on: "eval: frappe.user.has_role('System Manager') || frappe.user.has_role('VetEdge Administrator')"
						},
						{
							label: "Product Activation",
							link_type: "DocType",
							link_to: "CoreEdge Product Activation",
							display_depends_on: "eval: frappe.user.has_role('System Manager') || frappe.user.has_role('VetEdge Administrator')"
						},
						{
							label: "License Profile",
							link_type: "DocType",
							link_to: "Veterinary License Profile",
							display_depends_on: "eval: frappe.user.has_role('System Manager')"
						}
					]
				},
				{
					label: "Workspace",
					items: [
						{
							label: "Dashboards",
							type: "Submenu",
							items: [
								{
									label: "Executive Dashboard",
									link_type: "Page",
									link_to: "vetedge-executive-dashboard",
									display_depends_on: "eval: frappe.user.has_role('System Manager') || frappe.user.has_role('VetEdge Administrator')"
								},
								{
									label: "Clinical Dashboard",
									link_type: "Page",
									link_to: "vetedge-clinical-dashboard",
									display_depends_on: "eval: frappe.user.has_role('System Manager') || frappe.user.has_role('VetEdge Administrator') || frappe.user.has_role('VetEdge Doctor') || frappe.user.has_role('Veterinary Nurse') || frappe.user.has_role('Branch Manager')"
								},
								{
									label: "Financial Dashboard",
									link_type: "Page",
									link_to: "veterinary-financial-dashboard",
									display_depends_on: "eval: frappe.user.has_role('System Manager') || frappe.user.has_role('VetEdge Administrator') || frappe.user.has_role('Accounts/Cashier') || frappe.user.has_role('Accounts Manager') || frappe.user.has_role('Sales Manager') || frappe.user.has_role('Branch Manager')"
								},
								{
									label: "Inventory / Dispensary Dashboard",
									link_type: "Page",
									link_to: "vetedge-inventory-dispensary-dashboard",
									display_depends_on: "eval: frappe.user.has_role('System Manager') || frappe.user.has_role('VetEdge Administrator') || frappe.user.has_role('Dispensary User') || frappe.user.has_role('Branch Manager')"
								},
								{
									label: "Lab Dashboard",
									link_type: "Page",
									link_to: "vetedge-lab-dashboard",
									display_depends_on: "eval: frappe.user.has_role('System Manager') || frappe.user.has_role('VetEdge Administrator') || frappe.user.has_role('VetEdge Doctor') || frappe.user.has_role('Veterinary Nurse') || frappe.user.has_role('Lab Technician') || frappe.user.has_role('Branch Manager')"
								},
								{
									label: "Vaccination Dashboard",
									link_type: "Page",
									link_to: "vetedge-vaccination-dashboard",
									display_depends_on: "eval: frappe.user.has_role('System Manager') || frappe.user.has_role('VetEdge Administrator') || frappe.user.has_role('VetEdge Doctor') || frappe.user.has_role('Veterinary Nurse') || frappe.user.has_role('Branch Manager')"
								},
								{
									label: "Boarding Dashboard",
									link_type: "Page",
									link_to: "vetedge-boarding-dashboard",
									display_depends_on: "eval: frappe.user.has_role('System Manager') || frappe.user.has_role('VetEdge Administrator') || frappe.user.has_role('VetEdge Front Desk') || frappe.user.has_role('Branch Manager')"
								},
								{
									label: "Grooming Dashboard",
									link_type: "Page",
									link_to: "vetedge-grooming-dashboard",
									display_depends_on: "eval: frappe.user.has_role('System Manager') || frappe.user.has_role('VetEdge Administrator') || frappe.user.has_role('VetEdge Groomer') || frappe.user.has_role('VetEdge Front Desk') || frappe.user.has_role('Branch Manager')"
								},
								{
									label: "Practitioner Performance Dashboard",
									link_type: "Page",
									link_to: "vetedge-practitioner-performance-dashboard",
									display_depends_on: "eval: frappe.user.has_role('System Manager') || frappe.user.has_role('VetEdge Administrator') || frappe.user.has_role('VetEdge Doctor') || frappe.user.has_role('Branch Manager')"
								},
								{
									label: "Branch Performance Dashboard",
									link_type: "Page",
									link_to: "vetedge-branch-performance-dashboard",
									display_depends_on: "eval: frappe.user.has_role('System Manager') || frappe.user.has_role('VetEdge Administrator') || frappe.user.has_role('Branch Manager')"
								}
							]
						},
						{
							label: "Branch Context",
							link_type: "DocType",
							link_to: "CoreEdge Branch Session"
						},
						{
							label: "Company Context",
							link_type: "DocType",
							link_to: "CoreEdge Context Switch Log"
						}
					]
				},
				{
					label: "Platform",
					items: [
						{
							label: "CoreEdge Settings",
							link_type: "DocType",
							link_to: "CoreEdge Settings"
						},
						{
							label: "CoreEdge Tenant",
							link_type: "DocType",
							link_to: "CoreEdge Tenant"
						},
						{
							label: "Product Activation",
							link_type: "DocType",
							link_to: "CoreEdge Product Activation"
						},
						{
							label: "Access Decision Log",
							link_type: "DocType",
							link_to: "CoreEdge Access Decision Log"
						},
						{
							label: "Branch Session",
							link_type: "DocType",
							link_to: "CoreEdge Branch Session"
						},
						{
							label: "Context Switch Log",
							link_type: "DocType",
							link_to: "CoreEdge Context Switch Log"
						}
					]
				}
			]
		});
	}

	register();
})();
