(function installVetEdgeReportProviderAdapter(global) {
	"use strict";

	const PRODUCT = "vetedge";
	const FALLBACK_KIND = "vetedge-fallback";

	function runtimeReports() {
		return global.EdgeSuiteReports || global.EdgeSuiteUI?.reports || global.EdgeUI?.reports || null;
	}

	function normalizeColumns(columns = []) {
		return (Array.isArray(columns) ? columns : []).map((column, index) => {
			if (typeof column === "string") {
				const [label, fieldname, fieldtype, width] = column.split(":");
				return {
					label: label || `Column ${index + 1}`,
					fieldname: fieldname || `column_${index + 1}`,
					fieldtype: fieldtype || "Data",
					width: Number(width || 0) || undefined,
				};
			}
			return {
				...column,
				label: column?.label || column?.fieldname || column?.key || `Column ${index + 1}`,
				fieldname: column?.fieldname || column?.key || `column_${index + 1}`,
				fieldtype: column?.fieldtype || column?.type || "Data",
			};
		});
	}

	function normalizePayload(payload = {}, request = {}) {
		const shared = runtimeReports();
		if (shared?.normalizePayload) return shared.normalizePayload(payload, request);
		const columns = normalizeColumns(payload.columns || []);
		const sourceRows = payload.rows || payload.result || [];
		const rows = (Array.isArray(sourceRows) ? sourceRows : []).map((row) => {
			if (!Array.isArray(row)) return row || {};
			return Object.fromEntries(columns.map((column, index) => [column.fieldname, row[index]]));
		});
		const start = Number(payload.start ?? request.start ?? 0) || 0;
		const total = Number(payload.total ?? payload.total_count ?? rows.length) || 0;
		return {
			columns,
			rows,
			summary: payload.summary || payload.report_summary || [],
			chart: payload.chart || null,
			total,
			start,
			page_length: Number(payload.page_length ?? request.page_length ?? rows.length) || 0,
			has_previous: start > 0,
			has_next: start + rows.length < total,
			metadata: payload.metadata || {},
		};
	}

	function queryReportRunner({ reportName, filters = {} }) {
		return new Promise((resolve, reject) => {
			frappe.call({
				method: "frappe.desk.query_report.run",
				args: {
					report_name: reportName,
					filters: JSON.stringify(filters || {}),
					ignore_prepared_report: 1,
					are_default_filters: false,
				},
				callback: (response) => resolve(response.message || {}),
				error: reject,
			});
		});
	}

	function fallbackQueryProvider(reportName) {
		return Object.freeze({
			kind: FALLBACK_KIND,
			reportName,
			supports_server_pagination: false,
			async load({ filters = {} } = {}) {
				const payload = await queryReportRunner({ reportName, filters });
				return normalizePayload(payload || {});
			},
			export: null,
		});
	}

	function ensureQueryProvider(reportKey, reportName = reportKey) {
		const shared = runtimeReports();
		const existing = shared?.getProvider?.(PRODUCT, reportKey);
		if (existing) return existing;
		const provider = shared?.createQueryReportProvider
			? shared.createQueryReportProvider({ reportName, run: queryReportRunner })
			: fallbackQueryProvider(reportName);
		shared?.registerProvider?.(PRODUCT, reportKey, provider);
		return provider;
	}

	function registerProvider(reportKey, provider) {
		if (!reportKey || !provider || typeof provider.load !== "function") return null;
		const shared = runtimeReports();
		if (!shared?.registerProvider) return null;
		shared.registerProvider(PRODUCT, reportKey, provider);
		return provider;
	}

	function registerPaginatedProvider(reportKey, options = {}) {
		const shared = runtimeReports();
		if (!shared?.createPaginatedReportProvider || !shared?.registerProvider) return null;
		const provider = shared.createPaginatedReportProvider({ key: reportKey, ...options });
		shared.registerProvider(PRODUCT, reportKey, provider);
		return provider;
	}

	function getProvider(reportKey) {
		return runtimeReports()?.getProvider?.(PRODUCT, reportKey) || null;
	}

	global.VetEdgeReportProviders = Object.freeze({
		product: PRODUCT,
		runtimeReports,
		normalizePayload,
		queryReportRunner,
		ensureQueryProvider,
		registerProvider,
		registerPaginatedProvider,
		getProvider,
	});
})(window);
