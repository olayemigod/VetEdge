function apply_veterinary_settings_labels(frm) {
	frm.page.set_title(__("Veterinary Settings"));
	frm.set_df_property("enable_vetedge", "label", __("Enable Veterinary"));
	frm.set_df_property(
		"enable_vetedge",
		"description",
		__("Master switch for Veterinary workflows. Disable only during controlled maintenance or migration.")
	);
	frm.set_df_property(
		"restrict_to_vetedge_doctypes",
		"description",
		__("If enabled, notifications are limited to Veterinary DocTypes or documents carrying the Veterinary source marker.")
	);
	frm.set_df_property(
		"vetedge_source_field",
		"description",
		__("Optional source field used to identify Veterinary-owned documents.")
	);
}

function mount_veterinary_settings_edgeui(frm) {
	apply_veterinary_settings_labels(frm);
	const $wrapper = $(frm.wrapper);
	$wrapper.addClass("veterinary-settings-edgeui-form");

	let $root = $wrapper.find(".veterinary-settings-edgeui-header").first();
	if (!$root.length) {
		$root = $('<div class="veterinary-settings-edgeui-header" data-edge-product="veterinary"></div>');
		const $layout = $wrapper.find(".form-layout").first();
		if ($layout.length) $root.insertBefore($layout);
		else $root.prependTo($wrapper);
	}

	frm.__veterinary_settings_edgeui_visit = (frm.__veterinary_settings_edgeui_visit || 0) + 1;
	const visit = frm.__veterinary_settings_edgeui_visit;

	frappe.require("edgeui.bundle.js", () => {
		if (frm.__veterinary_settings_edgeui_visit !== visit) return;
		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		if (!runtime?.createEdgeApp || !runtime?.components?.EdgePageHeader || !runtime?.components?.EdgeStatusBadge) {
			console.warn("Veterinary Settings requires EdgeSuite UI 0.4.1 or newer.");
			return;
		}
		frappe.require("veterinary_settings_edgeui.bundle.js", () => {
			if (frm.__veterinary_settings_edgeui_visit !== visit || !window.mountVeterinarySettingsHeader) return;
			if (frm.__veterinary_settings_edgeui_app) {
				frm.__veterinary_settings_edgeui_app.unmount();
				frm.__veterinary_settings_edgeui_app = null;
			}
			$root.empty();
			frm.__veterinary_settings_edgeui_app = window.mountVeterinarySettingsHeader($root[0], {
				brandName: frm.doc.portal_brand_name || "",
				logoUrl: frm.doc.portal_logo || "",
			});
		});
	});
}

frappe.ui.form.on("Veterinary Settings", {
	onload(frm) {
		frm.set_query("consultation_item", () => ({
			filters: { disabled: 0, is_sales_item: 1, is_stock_item: 0 },
		}));
		frm.set_query("registration_fee_item", () => ({
			filters: { disabled: 0, is_sales_item: 1, is_stock_item: 0 },
		}));
		frm.set_query("default_laboratory_service_item", () => ({
			filters: { disabled: 0, is_sales_item: 1, is_stock_item: 0 },
		}));
	},

	refresh(frm) {
		mount_veterinary_settings_edgeui(frm);
		frm.trigger("toggle_consultation_item_editability");
		if (!frm.is_new()) {
			frm.set_df_property("enable_vetedge", "read_only", 1);
			frm.set_df_property(
				"enable_vetedge",
				"description",
				__("Master Veterinary switch. Contact a System Manager to change this after initial setup.")
			);
		}
	},

	portal_brand_name(frm) {
		mount_veterinary_settings_edgeui(frm);
	},

	portal_logo(frm) {
		mount_veterinary_settings_edgeui(frm);
	},

	auto_add_default_consultation_billing_item(frm) {
		frm.trigger("toggle_consultation_item_editability");
	},

	allow_editing_consultation_billing_item(frm) {
		frm.trigger("toggle_consultation_item_editability");
	},

	toggle_consultation_item_editability(frm) {
		const autoAdd = Boolean(frm.doc.auto_add_default_consultation_billing_item);
		const allowEditing = Boolean(frm.doc.allow_editing_consultation_billing_item);
		frm.set_df_property("consultation_item", "reqd", autoAdd ? 1 : 0);
		frm.set_df_property("consultation_item", "read_only", autoAdd && !allowEditing ? 1 : 0);
		frm.set_df_property(
			"consultation_item",
			"description",
			autoAdd
				? allowEditing
					? __("This item is added automatically to consultation invoices and may be changed here.")
					: __("This item is added automatically to consultation invoices and is locked by policy.")
				: __("Automatic consultation charge is disabled. Only explicit billable rows are invoiced.")
		);
		frm.refresh_field("consultation_item");
	},
});
