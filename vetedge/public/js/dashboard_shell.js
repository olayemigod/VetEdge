(function () {
	function escapeHtml(value) {
		return frappe.utils.escape_html(value == null ? "" : String(value));
	}

	function renderKpis(kpis) {
		if (!kpis || !kpis.length) {
			return '<div class="text-muted small">No KPI data yet.</div>';
		}
		return `
			<div class="row">
				${kpis
					.map(
						(kpi) => `
							<div class="col-md-4 mb-3">
								<div class="border rounded p-3 bg-white">
									<div class="text-muted small">${escapeHtml(kpi.label)}</div>
									<div style="font-size: 1.4rem; font-weight: 600;">${escapeHtml(kpi.value)}</div>
								</div>
							</div>
						`
					)
					.join("")}
			</div>
		`;
	}

	function renderLinks(reportLinks) {
		if (!reportLinks || !reportLinks.length) {
			return "";
		}
		return `
			<div class="mb-4">
				<div class="text-muted small mb-2">Quick Reports</div>
				<div class="d-flex flex-wrap" style="gap: 8px;">
					${reportLinks
						.map(
							(link) => `
								<button class="btn btn-default btn-sm vetedge-dashboard-report" data-report="${escapeHtml(link.report)}">
									${escapeHtml(link.label)}
								</button>
							`
						)
						.join("")}
				</div>
			</div>
		`;
	}

	function renderChartTable(chart) {
		const rows = chart.rows || [];
		const columns = chart.columns || [];
		if (!rows.length) {
			return `<div class="text-muted small">${escapeHtml(chart.empty_state || "No data available.")}</div>`;
		}
		if (!columns.length) {
			return `<div class="text-muted small">${escapeHtml(chart.empty_state || "No table columns configured.")}</div>`;
		}
		return `
			<div class="table-responsive vetedge-dashboard-chart-table">
				<table class="table table-sm table-bordered mb-0">
					<thead>
						<tr>
							${columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join("")}
						</tr>
					</thead>
					<tbody>
						${rows
							.map(
								(row) => `
									<tr>
										${columns.map((column) => `<td>${escapeHtml(row[column.fieldname])}</td>`).join("")}
									</tr>
								`
							)
							.join("")}
					</tbody>
				</table>
			</div>
		`;
	}

	function renderCharts(wrapper, charts) {
		const chartArea = wrapper.find(".vetedge-dashboard-charts");
		chartArea.empty();
		if (!charts || !charts.length) {
			chartArea.html('<div class="text-muted small">No chart data available for the current filters.</div>');
			return;
		}

		charts.forEach((chart, index) => {
			const chartId = `vetedge-dashboard-chart-${index}`;
			chartArea.append(`
				<div class="col-md-6 mb-4">
					<div class="border rounded p-3 bg-white h-100">
						<div class="mb-2" style="font-weight: 600;">${escapeHtml(chart.title || "Chart")}</div>
						<div id="${chartId}" style="min-height: 280px;"></div>
					</div>
				</div>
			`);
			const chartTarget = wrapper.find(`#${chartId}`);
			if (!(chart.data && chart.data.labels && chart.data.labels.length)) {
				chartTarget.html(renderChartTable(chart));
				return;
			}
			if (!frappe.Chart) {
				chartTarget.html(renderChartTable(chart));
				return;
			}
			try {
				new frappe.Chart(`#${chartId}`, {
					title: chart.title || "",
					data: chart.data,
					type: chart.type || "bar",
					colors: chart.colors || ["#5b8def"],
					barOptions: chart.barOptions || { stacked: 0 },
					height: 260,
				});
			} catch (error) {
				console.warn("VetEdge dashboard chart failed to render", error);
				chartTarget.html(renderChartTable(chart));
			}
		});
	}

	function buildFilters(page, state, refresh, config) {
		const branchField = page.add_field({
			label: __("Branch"),
			fieldname: "branch",
			fieldtype: "Link",
			options: "Branch",
			change() {
				state.branch = branchField.get_value();
				refresh();
			},
		});
		const fromField = page.add_field({
			label: __("From Date"),
			fieldname: "from_date",
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			change() {
				state.from_date = fromField.get_value();
				refresh();
			},
		});
		const toField = page.add_field({
			label: __("To Date"),
			fieldname: "to_date",
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			change() {
				state.to_date = toField.get_value();
				refresh();
			},
		});
		state.branch = branchField.get_value();
		state.from_date = fromField.get_value();
		state.to_date = toField.get_value();
		if (window.vetedgeReportVisibility && typeof window.vetedgeReportVisibility.applyDashboard === "function") {
			window.vetedgeReportVisibility.applyDashboard(branchField, config.key);
		}
		page.set_primary_action(__("Refresh"), refresh);
	}

	window.vetedgeDashboardShell = {
		mount(page, config) {
			const state = {};
			page.set_title(config.title);
			buildFilters(page, state, refresh, config);
			const wrapper = $(
				`<div class="vetedge-dashboard-root">
					<div class="vetedge-dashboard-links"></div>
					<div class="vetedge-dashboard-kpis"></div>
					<div class="row vetedge-dashboard-charts"></div>
				</div>`
			).appendTo(page.body);

			wrapper.on("click", ".vetedge-dashboard-report", function () {
				const report = $(this).data("report");
				if (report) {
					frappe.set_route("query-report", report);
				}
			});

			function refresh() {
				wrapper.find(".vetedge-dashboard-kpis").html('<div class="text-muted small">Loading dashboard...</div>');
				wrapper.find(".vetedge-dashboard-charts").empty();
				frappe.call({
					method: "vetedge.services.reporting_logic_v4.get_dashboard_payload",
					args: {
						dashboard_key: config.key,
						filters: state,
					},
					callback: function (r) {
						const payload = r.message || {};
						wrapper.find(".vetedge-dashboard-links").html(renderLinks(payload.report_links));
						wrapper.find(".vetedge-dashboard-kpis").html(renderKpis(payload.kpis));
						renderCharts(wrapper, payload.charts || []);
					},
				});
			}

			refresh();
		},
	};
})();
