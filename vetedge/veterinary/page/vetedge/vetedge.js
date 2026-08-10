frappe.pages["vetedge"].on_page_load = function (wrapper) {
	wrapper.page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Veterinary Home"),
		single_column: true,
	});
};

frappe.pages["vetedge"].on_page_show = function (wrapper) {
	if (wrapper.__vetedge_home_redirecting) return;
	wrapper.__vetedge_home_redirecting = true;
	const target = "/app/vetedge-resource-center";
	window.location.replace(target);
};
