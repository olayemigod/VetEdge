frappe.pages["vetedge-notification-items"].on_page_load = function (wrapper) {
	wrapper.page = frappe.ui.make_app_page({ parent: wrapper, title: __("Notification Items"), single_column: true });
};
frappe.pages["vetedge-notification-items"].on_page_show = function () {
	const target = "/desk/vetedge-administration?resource=notification-items";
	window.setTimeout(() => {
		if (window.history && typeof frappe?.router?.route === "function") {
			window.history.replaceState(window.history.state, "", target);
			Promise.resolve(frappe.router.route()).catch(() => window.location.replace(target));
			return;
		}
		window.location.replace(target);
	}, 0);
};
