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

	const target = "/desk/vetedge-resource-center";
	const finishRedirect = () => {
		wrapper.__vetedge_home_redirecting = false;
	};

	if (typeof frappe.set_route === "function") {
		try {
			Promise.resolve(frappe.set_route("vetedge-resource-center")).finally(finishRedirect);
		} catch (_error) {
			finishRedirect();
			window.location.assign(target);
		}
		return;
	}

	finishRedirect();
	window.location.assign(target);
};
