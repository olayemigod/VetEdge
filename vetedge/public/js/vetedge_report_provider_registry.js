(function installVetEdgeReferenceReportProviders(global) {
	"use strict";

	const STOCK_EXPIRY_COLUMNS = [
		{ fieldname: "item_code", label: "Item Code", fieldtype: "Link", options: "Item" },
		{ fieldname: "item_name", label: "Item Name", fieldtype: "Data" },
		{ fieldname: "batch_no", label: "Batch No", fieldtype: "Link", options: "Batch" },
		{ fieldname: "warehouse", label: "Warehouse", fieldtype: "Link", options: "Warehouse" },
		{ fieldname: "qty", label: "Quantity", fieldtype: "Float" },
		{ fieldname: "stock_uom", label: "UOM", fieldtype: "Data" },
		{ fieldname: "expiry_date", label: "Expiry Date", fieldtype: "Date" },
		{ fieldname: "days_to_expiry", label: "Days Left", fieldtype: "Int" },
		{ fieldname: "expiry_status", label: "Risk Status", fieldtype: "Data" },
		{ fieldname: "branch", label: "Branch", fieldtype: "Link", options: "Branch" },
	];

	function call(method, args = {}) {
		return new Promise((resolve, reject) => {
			if (!global.frappe?.call) {
				reject(new Error("Frappe Desk is not ready."));
				return;
			}
			global.frappe.call({
				method,
				args,
				callback: (response) => resolve(response.message || {}),
				error: reject,
			});
		});
	}

	function adapter() {
		return global.VetEdgeReportProviders || null;
	}

	function stockFilters(filters = {}, start = 0, pageLength = 50) {
		return {
			warehouse: filters.warehouse || "",
			item_group: filters.item_group || "",
			expiry_window: filters.expiry_window || "all",
			days_threshold: Number(filters.days_threshold || 60),
			item: filters.item || "",
			limit: pageLength,
			offset: start,
		};
	}

	function stockSummaryCards(summary = {}) {
		return [
			{ label: "Expired Batches", value: Number(summary.expired_items || 0), datatype: "Int" },
			{ label: "Expiring Soon", value: Number(summary.expiring_soon || 0), datatype: "Int" },
			{ label: "Affected Total Qty", value: Number(summary.affected_qty || 0), datatype: "Float" },
			{ label: "Affected Warehouses", value: Number(summary.affected_warehouses || 0), datatype: "Int" },
			{ label: "Highest Risk Items", value: Number(summary.highest_risk_items || 0), datatype: "Int" },
		].filter((card) => Number.isFinite(card.value));
	}

	function registerStockExpiry() {
		const reports = adapter();
		if (!reports?.registerPaginatedProvider || reports.getProvider("Stock Expiry Report")) return;
		const provider = reports.registerPaginatedProvider("Stock Expiry Report", {
			defaultPageLength: 50,
			maxPageLength: 100,
			loadPage: async ({ filters = {}, start = 0, page_length = 50 }) => {
				const payload = await call(
					"vetedge.veterinary.page.stock_expiry_monitor.stock_expiry_monitor.get_stock_expiry_data",
					{ filters: stockFilters(filters, start, page_length) },
				);
				return {
					columns: STOCK_EXPIRY_COLUMNS,
					rows: payload.rows || [],
					summary: stockSummaryCards(payload.summary || {}),
					total_count: Number(payload.total_count || 0),
					start,
					page_length,
					metadata: { pagination_mode: "query-level", source: "stock-expiry-monitor" },
				};
			},
		});
		if (provider) reports.registerProvider("Stock Expiry Monitor", provider);
	}

	function registerPlannedTreatment() {
		const reports = adapter();
		if (!reports?.registerPaginatedProvider || reports.getProvider("Planned Treatment")) return;
		const provider = reports.registerPaginatedProvider("Planned Treatment", {
			defaultPageLength: 50,
			maxPageLength: 100,
			loadPage: async ({ filters = {}, start = 0, page_length = 50 }) => {
				const payload = await call("vetedge.services.treatment_plan_report.get_planned_treatment_view", {
					filters,
					start,
					page_length,
				});
				return {
					...payload,
					total_count: Number(payload.total || 0),
					metadata: {
						...(payload.metadata || {}),
						pagination_mode: payload.metadata?.pagination_mode || "query-level-detail",
						source: "planned-treatment",
					},
				};
			},
		});
		if (provider) reports.registerProvider("Planned Treatment Report", provider);
	}

	function registerServerPaginatedReport(reportKey, method, aliases = []) {
		const reports = adapter();
		if (!reports?.registerPaginatedProvider || reports.getProvider(reportKey)) return;
		const provider = reports.registerPaginatedProvider(reportKey, {
			defaultPageLength: 50,
			maxPageLength: 100,
			loadPage: async ({ filters = {}, start = 0, page_length = 50 }) => {
				const payload = await call(method, { filters, start, page_length });
				return {
					...payload,
					total_count: Number(payload.total || payload.total_count || 0),
					metadata: {
						...(payload.metadata || {}),
						pagination_mode: payload.metadata?.pagination_mode || "query-level",
					},
				};
			},
		});
		if (provider) aliases.forEach((alias) => reports.registerProvider(alias, provider));
	}

	function registerClinicalReports() {
		registerServerPaginatedReport(
			"Consultation Register",
			"vetedge.services.consultation_report.get_consultation_register_view",
		);
		registerServerPaginatedReport(
			"Lab Order Report",
			"vetedge.services.lab_order_report.get_lab_order_report_view",
			["Laboratory Report"],
		);
		registerServerPaginatedReport(
			"Vaccination Report",
			"vetedge.services.vaccination_report.get_vaccination_report_view",
		);
	}

	function registerMasterReports() {
		registerServerPaginatedReport(
			"Owner Register",
			"vetedge.services.owner_report.get_owner_register_view",
		);
	}

	function register() {
		if (!adapter()?.runtimeReports?.()) return false;
		registerStockExpiry();
		registerPlannedTreatment();
		registerClinicalReports();
		registerMasterReports();
		return true;
	}

	global.VetEdgeReportProviderRegistry = Object.freeze({ register });
	if (!register()) global.addEventListener?.("edgesuite:report-runtime-ready", register, { once: true });
})(window);
