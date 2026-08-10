frappe.pages["veterinary-settings-center"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Veterinary Settings"),
		single_column: true,
	});
	page.main.addClass("veterinary-settings-center-page");

	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visitId = wrapper.current_visit_id;
	const root = document.createElement("div");
	root.className = "veterinary-settings-center-root";
	root.dataset.edgeProduct = "veterinary";
	page.body.empty().append(root);

	frappe.require("edgeui.bundle.js", () => {
		if (wrapper.current_visit_id !== visitId) return;
		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		const required = [
			"EdgeAppShell",
			"EdgePageLayout",
			"EdgePageHeader",
			"EdgeStatusBadge",
			"EdgeLinkField",
			"EdgeDropdown",
			"EdgeInput",
			"EdgeTextarea",
			"EdgeCheckbox",
			"EdgeLoadingState",
			"EdgeErrorState",
		];
		const missing = required.filter((name) => !runtime?.components?.[name]);
		if (!runtime?.createEdgeApp || missing.length) {
			root.innerHTML = `<div class="alert alert-danger">${__("EdgeSuite UI 0.6.3 or newer is required for Veterinary Settings. Missing: {0}", [missing.join(", ")])}</div>`;
			return;
		}
		frappe.require("vetedge_professional_ui.js", () => {
			window.VetEdgeUIBridge?.install?.();
			frappe.require("veterinary_settings_center.bundle.js", () => {
				if (wrapper.current_visit_id !== visitId || !window.mountVeterinarySettingsCenter) return;
				wrapper.__veterinarySettingsApp?.unmount?.();
				wrapper.__veterinarySettingsApp = window.mountVeterinarySettingsCenter(root);
			});
		});
	});
};

frappe.pages["veterinary-settings-center"].on_page_show = function (wrapper) {
	window.VetEdgeUIBridge?.install?.();
	wrapper.__veterinarySettingsApp?.view?.reload?.();
};

frappe.pages["veterinary-settings-center"].on_page_unload = function (wrapper) {
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	wrapper.__veterinarySettingsApp?.unmount?.();
	wrapper.__veterinarySettingsApp = null;
};
