(function () {
	function escapeHtml(value) {
		return frappe.utils.escape_html(value == null ? "" : String(value));
	}

	function formatCurrency(val) {
		if (typeof val !== "number") return val;
		if (frappe.format_value) {
			return frappe.format_value(val, {fieldtype: "Currency"});
		}
		return "₦" + val.toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,');
	}

	function roundValue(val, precision = 2) {
		const num = Number(val);
		return isNaN(num) ? val : num.toFixed(precision);
	}

	function renderTrend(trend) {
		if (!trend || trend.direction === "flat") {
			return "";
		}
		const colorClass = trend.direction === "up" ? "text-success" : "text-danger";
		const symbol = trend.direction === "up" ? "▲" : "▼";
		return `<span class="${colorClass} ml-2 font-weight-bold" style="font-size: 0.85rem;">${symbol} ${trend.percentage}%</span>`;
	}

	function cardFormatterType(card, fallback = "raw") {
		const valueType = String(card.value_type || card.fieldtype || card.format || "").toLowerCase();
		if (valueType === "currency") return "currency";
		if (valueType === "percent") return "percent";
		return fallback;
	}

	function renderGenericCard(card, formatterType = "raw") {
		formatterType = cardFormatterType(card, formatterType);
		const actionAttr = card.action 
			? `class="border rounded p-3 bg-white vetedge-dashboard-kpi-card h-100 edge-suite-interactive-card" style="cursor: pointer;" data-action="${escapeHtml(JSON.stringify(card.action))}"` 
			: 'class="border rounded p-3 bg-white h-100"';
		
		let formattedValue = card.value;
		if (formatterType === "currency" && typeof card.value === "number") {
			formattedValue = formatCurrency(card.value);
		} else if (formatterType === "percent" && typeof card.value === "number") {
			formattedValue = `${roundValue(card.value, 1)}%`;
		}
		
		const trendHtml = renderTrend(card.trend);
		const secondaryHtml = card.secondary_value 
			? `<div class="text-muted mt-1" style="font-size: 0.8rem;">${escapeHtml(card.secondary_value)}</div>` 
			: "";
		const tooltipAttr = card.tooltip ? `title="${escapeHtml(card.tooltip)}"` : "";

		return `
			<div ${actionAttr} ${tooltipAttr}>
				<div class="text-muted small d-flex justify-content-between align-items-center">
					<span>${escapeHtml(card.title || card.label)}</span>
					${trendHtml}
				</div>
				<div class="mt-2 font-weight-bold" style="font-size: 1.3rem; color: var(--edge-text); font-family: var(--edge-font, inherit);">${escapeHtml(formattedValue)}</div>
				${secondaryHtml}
			</div>
		`;
	}

	function renderProgressCard(card) {
		const trendHtml = renderTrend(card.trend);
		const percent = Math.min(Math.max(Number(card.value) || 0, 0), 100);
		const barColor = percent >= 80 ? "bg-success" : (percent >= 50 ? "bg-warning" : "bg-danger");
		const tooltipAttr = card.tooltip ? `title="${escapeHtml(card.tooltip)}"` : "";

		return `
			<div class="border rounded p-3 bg-white h-100" ${tooltipAttr}>
				<div class="text-muted small d-flex justify-content-between align-items-center">
					<span>${escapeHtml(card.title || card.label)}</span>
					${trendHtml}
				</div>
				<div class="mt-2 font-weight-bold" style="font-size: 1.3rem; color: var(--edge-text);">${roundValue(percent, 1)}%</div>
				<div class="progress mt-2" style="height: 6px; border-radius: 3px; background-color: var(--edge-border, #dfe5ef);">
					<div class="progress-bar ${barColor}" role="progressbar" style="width: ${percent}%;" aria-valuenow="${percent}" aria-valuemin="0" aria-valuemax="100"></div>
				</div>
				${card.secondary_value ? `<div class="text-muted mt-2" style="font-size: 0.8rem;">${escapeHtml(card.secondary_value)}</div>` : ""}
			</div>
		`;
	}

	function renderKpis(kpis) {
		if (!kpis || !kpis.length) {
			return '<div class="text-muted small">No KPI data yet.</div>';
		}
		return `
			<div class="row">
				${kpis
					.map(
						(kpi) => {
							const isRich = kpi.id || kpi.trend || kpi.secondary_value || kpi.tooltip;
							if (isRich) {
								const actionAttr = kpi.action 
									? `class="border rounded p-3 bg-white vetedge-dashboard-kpi-card h-100 edge-suite-interactive-card" style="cursor: pointer;" data-action="${escapeHtml(JSON.stringify(kpi.action))}"` 
									: 'class="border rounded p-3 bg-white h-100"';
								
								let formattedValue = kpi.value;
								const formatType = cardFormatterType(kpi);
								if (formatType === "currency" && typeof kpi.value === "number") formattedValue = formatCurrency(kpi.value);
								if (formatType === "percent" && typeof kpi.value === "number") formattedValue = `${roundValue(kpi.value, 1)}%`;
								if (String(kpi.value_type || kpi.fieldtype || "").toLowerCase() === "integer" && typeof kpi.value === "number") formattedValue = String(Math.round(kpi.value));
								
								const trendHtml = renderTrend(kpi.trend);
								const secondaryHtml = kpi.secondary_value 
									? `<div class="text-muted mt-1" style="font-size: 0.8rem;">${escapeHtml(kpi.secondary_value)}</div>` 
									: "";
								const tooltipAttr = kpi.tooltip ? `title="${escapeHtml(kpi.tooltip)}"` : "";

								return `
									<div class="col-md mb-3">
										<div ${actionAttr} ${tooltipAttr}>
											<div class="text-muted small d-flex justify-content-between align-items-center">
												<span>${escapeHtml(kpi.title || kpi.label)}</span>
												${trendHtml}
											</div>
											<div class="mt-2 font-weight-bold" style="font-size: 1.3rem; color: var(--edge-text); font-family: var(--edge-font, inherit);">${escapeHtml(formattedValue)}</div>
											${secondaryHtml}
										</div>
									</div>
								`;
							} else {
								const actionAttr = kpi.action ? `class="border rounded p-3 bg-white vetedge-dashboard-kpi-card" style="cursor: pointer;" data-action="${escapeHtml(JSON.stringify(kpi.action))}"` : 'class="border rounded p-3 bg-white"';
								return `
									<div class="col-md mb-3">
										<div ${actionAttr}>
											<div class="text-muted small">${escapeHtml(kpi.label || kpi.title)}</div>
											<div style="font-size: 1.4rem; font-weight: 600;">${escapeHtml(kpi.value)}</div>
										</div>
									</div>
								`;
							}
						}
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

	function renderAlerts(alerts) {
		if (!alerts || !alerts.length) {
			return "";
		}
		return `
			<div class="edge-alerts-container mb-4">
				${alerts.map(alert => {
					const alertClass = alert.severity === "danger" ? "alert-danger" : (alert.severity === "warning" ? "alert-warning" : "alert-info");
					const icon = alert.severity === "danger" ? "⚠️" : (alert.severity === "warning" ? "🔔" : "💡");
					const actionBtn = alert.action 
						? `<button class="btn btn-xs btn-outline-secondary ml-3 vetedge-dashboard-kpi-card" data-action="${escapeHtml(JSON.stringify(alert.action))}">View Details →</button>`
						: "";
					return `
						<div class="alert ${alertClass} d-flex align-items-center justify-content-between p-3 mb-2" style="border-radius: 8px; border: 1px solid rgba(0,0,0,0.03);">
							<div class="d-flex align-items-center">
								<span style="font-size: 1.2rem; margin-right: 12px;">${icon}</span>
								<div>
									<div style="font-weight: 600; font-size: 0.9rem;">${escapeHtml(alert.title)}</div>
									<div style="font-size: 0.85rem; opacity: 0.9;">${escapeHtml(alert.description)}</div>
								</div>
							</div>
							<div class="d-flex align-items-center">
								<span class="badge badge-light p-2 font-weight-bold" style="font-size: 0.85rem;">${escapeHtml(alert.supporting_metric)}</span>
								${actionBtn}
							</div>
						</div>
					`;
				}).join("")}
			</div>
		`;
	}

	function renderCollectionMetrics(metrics) {
		if (!metrics || !metrics.length) return "";
		return `
			<div class="row">
				${metrics.map(card => {
					if (card.id === "collection_rate") {
						return `<div class="col-md-3 mb-3">${renderProgressCard(card)}</div>`;
					}
					return `<div class="col-md-3 mb-3">${renderGenericCard(card, cardFormatterType(card))}</div>`;
				}).join("")}
			</div>
		`;
	}

	function renderRevenueComposition(container, composition) {
		clearChartInstances(container);
		if (!composition || !composition.length) {
			container.html('<div class="vetedge-revenue-composition-empty">No revenue recorded for the selected period.</div>');
			return;
		}

		const entries = composition.filter((card) => Number(card.value) > 0);
		const total = entries.reduce((sum, card) => sum + Number(card.value || 0), 0);
		if (!entries.length || !total) {
			container.html('<div class="vetedge-revenue-composition-empty">No revenue recorded for the selected period.</div>');
			return;
		}

		const palette = ["#1677ff", "#16a34a", "#8b5cf6", "#f59e0b", "#ec4899", "#0ea5e9", "#14b8a6", "#f97316"];
		container.html(`
			<section class="vetedge-revenue-composition-panel">
				<header class="vetedge-revenue-composition-header">
					<div><h3>Revenue Composition</h3><p>Revenue mix for the selected branch and date range.</p></div>
					<button class="btn btn-default btn-sm vetedge-dashboard-report" data-report="Revenue Summary">View Report</button>
				</header>
				<div class="vetedge-revenue-composition-cards">
					${entries.map((card, index) => {
						const share = Number(card.share_percent ?? ((Number(card.value) / total) * 100));
						return `<article class="vetedge-revenue-composition-card">
							<div class="vetedge-revenue-composition-marker" style="background:${palette[index % palette.length]}"></div>
							<div class="vetedge-revenue-composition-name">${escapeHtml(card.title)}</div>
							<div class="vetedge-revenue-composition-amount">${escapeHtml(formatChartValue(card.value, card))}</div>
							<div class="vetedge-revenue-composition-share">${roundValue(share, 1)}% of Revenue</div>
							<div class="vetedge-revenue-composition-progress"><span style="width:${Math.min(share, 100)}%; background:${palette[index % palette.length]}"></span></div>
						</article>`;
					}).join("")}
				</div>
				<div class="vetedge-revenue-composition-chart-layout">
					<div class="vetedge-revenue-composition-donut-wrap">
						<div class="vetedge-revenue-composition-donut" id="vetedge-revenue-composition-chart"></div>
						<div class="vetedge-revenue-composition-total"><span>Total Revenue</span><strong>${escapeHtml(formatCurrency(total))}</strong></div>
					</div>
					<div class="vetedge-revenue-composition-legend">
						${entries.map((card, index) => `<div><i style="background:${palette[index % palette.length]}"></i><span>${escapeHtml(card.title)}</span><strong>${escapeHtml(formatChartValue(card.value, card))}</strong></div>`).join("")}
					</div>
				</div>
			</section>`);

		const chart = {
			title: "Revenue Composition", type: "donut", value_type: "currency", fieldtype: "Currency",
			data: { labels: entries.map((card) => card.title), datasets: [{ name: "Revenue", values: entries.map((card) => Number(card.value)) }] },
			colors: entries.map((card, index) => palette[index % palette.length]),
		};
		renderChartWhenReady({ wrapper: container, container: container.find("#vetedge-revenue-composition-chart"), chart });
	}


	function renderHealthIndicators(health) {
		if (!health || !health.length) return "";
		return `
			<div class="row">
				${health.map(card => {
					if (card.id === "billing_completion_rate" || card.id === "payment_completion_rate") {
						return `<div class="col-md-4 mb-3">${renderProgressCard(card)}</div>`;
					}
					return `<div class="col-md-4 mb-3">${renderGenericCard(card, "raw")}</div>`;
				}).join("")}
			</div>
		`;
	}

	function renderOutstandingBreakdowns(breakdowns) {
		if (!breakdowns) return "";
		
		const top5 = breakdowns.top_outstanding_balances || [];
		
		const renderRankingList = (title, items) => {
			if (!items || !items.length) {
				return `<div class="text-muted small p-3 text-center">No outstanding records.</div>`;
			}
			const maxVal = Math.max(...items.map(item => Number(item.value) || 1));
			return `
				<div class="p-3 bg-white border rounded h-100">
					<div class="font-weight-bold mb-3 text-muted small" style="letter-spacing: 0.5px; text-transform: uppercase;">${escapeHtml(title)}</div>
					<div class="d-flex flex-column" style="gap: 12px;">
						${items.slice(0, 5).map(item => {
							const pct = (item.value / maxVal) * 100;
							return `
								<div>
									<div class="d-flex justify-content-between small mb-1">
										<span class="font-weight-bold text-truncate" style="max-width: 180px;">${escapeHtml(item.name)}</span>
										<span style="color: var(--edge-text); font-weight: 600;">${formatCurrency(item.value)}</span>
									</div>
									<div class="progress" style="height: 5px; border-radius: 2px;">
										<div class="progress-bar bg-info" role="progressbar" style="width: ${pct}%;"></div>
									</div>
								</div>
							`;
						}).join("")}
					</div>
				</div>
			`;
		};

		const top5Html = `
			<div class="col-12 mb-4">
				<div class="p-3 bg-white border rounded">
					<div class="font-weight-bold mb-3 text-muted small" style="letter-spacing: 0.5px; text-transform: uppercase;">Top 5 Outstanding Customer Invoices</div>
					<div class="table-responsive">
						<table class="table table-sm table-hover mb-0" style="font-size: 0.85rem;">
							<thead>
								<tr>
									<th>Invoice</th>
									<th>Customer</th>
									<th class="text-right">Outstanding Amount</th>
									<th class="text-right">Days Overdue</th>
								</tr>
							</thead>
							<tbody>
								${top5.map(inv => `
									<tr class="vetedge-dashboard-kpi-card" style="cursor: pointer;" data-action='{"type":"report","target":"Unpaid Invoice Report","filters":{}}'>
										<td style="font-weight: 600; color: var(--edge-primary);">${escapeHtml(inv.sales_invoice)}</td>
										<td>${escapeHtml(inv.customer)}</td>
										<td class="text-right font-weight-bold text-danger">${formatCurrency(inv.outstanding_amount)}</td>
										<td class="text-right">${inv.days_overdue} Days</td>
									</tr>
								`).join("")}
								${!top5.length ? `<tr><td colspan="4" class="text-center text-muted">No outstanding balances found.</td></tr>` : ""}
							</tbody>
						</table>
					</div>
				</div>
			</div>
		`;

		return `
			${top5Html}
			<div class="col-md-6 mb-3">${renderRankingList("Outstanding by Branch", breakdowns.by_branch)}</div>
			<div class="col-md-6 mb-3">${renderRankingList("Outstanding by Service Area", breakdowns.by_service)}</div>
			<div class="col-md-6 mb-3">${renderRankingList("Outstanding by Customer", breakdowns.by_customer)}</div>
			<div class="col-md-6 mb-3">${renderRankingList("Outstanding by Practitioner", breakdowns.by_doctor)}</div>
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

	function formatChartValue(value, chart) {
		const valueType = cardFormatterType(chart);
		if (valueType === "currency" && typeof value === "number") return formatCurrency(value);
		if (valueType === "percent" && typeof value === "number") return `${roundValue(value, 1)}%`;
		if (valueType === "integer" && typeof value === "number") return String(Math.round(value));
		if (valueType === "float" && typeof value === "number") return roundValue(value, 2);
		return value;
	}

	function clearChartInstances(wrapper) {
		(wrapper._chartInstances || []).forEach((instance) => {
			if (instance && typeof instance.destroy === "function") instance.destroy();
		});
		wrapper._chartInstances = [];
	}

	function renderChartWhenReady({ wrapper, container, chart, maxAttempts = 5, attempt = 0 }) {
		requestAnimationFrame(() => {
			const element = container && container.get(0);
			const ready = element && element.isConnected && element.offsetWidth > 0 && element.offsetHeight > 0 && frappe.Chart;
			if (!ready && attempt < maxAttempts - 1) {
				renderChartWhenReady({ wrapper, container, chart, maxAttempts, attempt: attempt + 1 });
				return;
			}
			if (!ready) { container.html(renderChartTable(chart)); return; }
			try {
				container.empty();
				const instance = new frappe.Chart(element, {
					title: chart.title || "", data: chart.data, type: chart.type || "bar",
					colors: chart.colors || ["#5b8def"], barOptions: chart.barOptions || { stacked: 0 }, height: 260,
					tooltipOptions: { formatTooltipY: (value) => formatChartValue(value, chart) },
				});
				wrapper._chartInstances.push(instance);
			} catch (error) {
				console.warn("VetEdge dashboard chart failed to render", error);
				container.html(renderChartTable(chart));
			}
		});
	}

	function renderCharts(wrapper, charts) {
		const chartArea = wrapper.find(".vetedge-dashboard-charts");
		clearChartInstances(wrapper);
		chartArea.empty();
		if (!charts || !charts.length) { chartArea.html('<div class="text-muted small">No chart data available for the current filters.</div>'); return; }
		charts.forEach((chart, index) => {
			const chartId = `vetedge-dashboard-chart-${index}`;
			chartArea.append(`<div class="col-md-6 mb-4"><div class="border rounded p-3 bg-white h-100"><div class="mb-2" style="font-weight: 600;">${escapeHtml(chart.title || "Chart")}</div><div id="${chartId}" style="min-height: 280px;"></div></div></div>`);
			const container = chartArea.find(`#${chartId}`);
			if (!(chart.data && chart.data.labels && chart.data.labels.length)) { container.html(renderChartTable(chart)); return; }
			renderChartWhenReady({ wrapper, container, chart });
		});
	}

	function buildFilters(page, state, refresh_fn, config) {
		const branchField = page.add_field({
			label: __("Branch"),
			fieldname: "branch",
			fieldtype: "Link",
			options: "Branch",
			default: state.branch,
			change() {
				state.branch = branchField.get_value();
				frappe.route_options = Object.assign({}, frappe.route_options, { branch: state.branch });
				refresh_fn();
			},
		});

		const presetField = page.add_field({
			label: "",
			fieldname: "date_preset",
			fieldtype: "Select",
			options: frappe.EdgeSuite.DateRanges.getOptions(),
			default: state.date_preset,
			change() {
				if (state.is_updating_dates || state.is_updating_preset) return;
				const val = presetField.get_value();
				if (val && val !== "custom") {
					frappe.EdgeSuite.DateRanges.applyPreset({ state, preset: val, presetField, fromField, toField, refresh: refresh_fn });
				} else {
					state.date_preset = "custom";
					frappe.route_options = Object.assign({}, frappe.route_options, { date_preset: "custom" });
				}
			}
		});

		const fromField = page.add_field({
			label: __("From Date"),
			fieldname: "from_date",
			fieldtype: "Date",
			default: state.from_date,
			change() {
				if (state.is_updating_preset) return;
				state.from_date = fromField.get_value();
				state.date_preset = "custom";
				
				state.is_updating_dates = true;
				presetField.set_value("custom");
				state.is_updating_dates = false;
				
				frappe.route_options = Object.assign({}, frappe.route_options, {
					from_date: state.from_date,
					date_preset: "custom"
				});
				refresh_fn();
			},
		});

		const toField = page.add_field({
			label: __("To Date"),
			fieldname: "to_date",
			fieldtype: "Date",
			default: state.to_date,
			change() {
				if (state.is_updating_preset) return;
				state.to_date = toField.get_value();
				state.date_preset = "custom";
				
				state.is_updating_dates = true;
				presetField.set_value("custom");
				state.is_updating_dates = false;
				
				frappe.route_options = Object.assign({}, frappe.route_options, {
					to_date: state.to_date,
					date_preset: "custom"
				});
				refresh_fn();
			},
		});

		state.branch = branchField.get_value();
		state.from_date = fromField.get_value();
		state.to_date = toField.get_value();

		if (window.vetedgeReportVisibility && typeof window.vetedgeReportVisibility.applyDashboard === "function") {
			window.vetedgeReportVisibility.applyDashboard(branchField, config.key);
		}
		page.set_primary_action(__("Refresh"), refresh_fn);
	}

	window.vetedgeDashboardShell = {
		mount(page, config) {
			const state = {};
			
			const route_opts = frappe.route_options || {};
			state.branch = route_opts.branch || "";
			state.date_preset = route_opts.date_preset || frappe.EdgeSuite.DateRanges.getDefaultPreset();
			
			if (route_opts.from_date && route_opts.to_date) {
				state.from_date = route_opts.from_date;
				state.to_date = route_opts.to_date;
				if (!route_opts.date_preset) {
					state.date_preset = "custom";
				}
			} else {
				const range = frappe.EdgeSuite.DateRanges.getRange(state.date_preset);
				if (range) {
					state.from_date = range.start;
					state.to_date = range.end;
				} else {
					state.from_date = frappe.datetime.month_start();
					state.to_date = frappe.datetime.get_today();
				}
			}

			let refresh_timeout = null;
			function debounced_refresh(afterRefresh) {
				if (refresh_timeout) clearTimeout(refresh_timeout);
				refresh_timeout = setTimeout(() => refresh(afterRefresh), 50);
			}

			page.set_title(config.title);
			buildFilters(page, state, debounced_refresh, config);

			
			const wrapper = $(
				`<div class="vetedge-dashboard-root container-fluid">
					<div class="vetedge-dashboard-alerts"></div>
					<div class="vetedge-dashboard-links"></div>
					
					<div class="vetedge-dashboard-kpi-section">
						<div class="vetedge-dashboard-section-title">Executive Summary</div>
						<div class="vetedge-dashboard-kpis"></div>
					</div>
					
					<div class="vetedge-dashboard-collection-section" style="display: none;">
						<div class="vetedge-dashboard-section-title">Collection Performance</div>
						<div class="vetedge-dashboard-collection"></div>
					</div>

					<div class="vetedge-dashboard-composition-section" style="display: none;">
						<div class="vetedge-dashboard-section-title">Revenue Composition</div>
						<div class="vetedge-dashboard-composition"></div>
					</div>

					<div class="vetedge-dashboard-health-section" style="display: none;">
						<div class="vetedge-dashboard-section-title">Financial Health &amp; Concentration</div>
						<div class="vetedge-dashboard-health"></div>
					</div>

					<div class="vetedge-dashboard-outstanding-section" style="display: none;">
						<div class="vetedge-dashboard-section-title">Outstanding Insights &amp; Rankings</div>
						<div class="row vetedge-dashboard-outstanding"></div>
					</div>

					<div class="vetedge-dashboard-trend-section">
						<div class="vetedge-dashboard-section-title">Performance Trends</div>
						<div class="row vetedge-dashboard-charts"></div>
					</div>
				</div>`
			).appendTo(page.body);

			wrapper.on("click", ".vetedge-dashboard-report", function () {
				const report = $(this).data("report");
				if (report) {
					frappe.route_options = {
						from_date: state.from_date,
						to_date: state.to_date,
						branch: state.branch
					};
					frappe.set_route("query-report", report);
				}
			});

			wrapper.on("click", ".vetedge-dashboard-kpi-card", function () {
				const actionStr = $(this).attr("data-action");
				if (actionStr) {
					const action = JSON.parse(actionStr);
					if (action.type === "report" && action.target) {
						const routeFilters = Object.assign({}, {
							from_date: state.from_date,
							to_date: state.to_date,
							branch: state.branch
						}, action.filters || {});
						frappe.route_options = routeFilters;
						frappe.set_route("query-report", action.target);
					}
				}
			});

			function refresh(afterRefresh) {
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
						
						// Render Quick Reports links
						wrapper.find(".vetedge-dashboard-links").html(renderLinks(payload.report_links));
						
						// Render Executive Summary KPIs
						wrapper.find(".vetedge-dashboard-kpis").html(renderKpis(payload.kpis));
						
						// Render dynamic alerts
						if (payload.alerts && payload.alerts.length) {
							wrapper.find(".vetedge-dashboard-alerts").html(renderAlerts(payload.alerts)).show();
						} else {
							wrapper.find(".vetedge-dashboard-alerts").empty().hide();
						}

						// Render Collection Performance
						if (payload.collection_metrics && payload.collection_metrics.length) {
							wrapper.find(".vetedge-dashboard-collection").html(renderCollectionMetrics(payload.collection_metrics));
							wrapper.find(".vetedge-dashboard-collection-section").show();
						} else {
							wrapper.find(".vetedge-dashboard-collection-section").hide();
						}

						// Render Revenue Composition
						if (payload.revenue_composition && payload.revenue_composition.length) {
							wrapper.find(".vetedge-dashboard-composition").html(renderRevenueComposition(wrapper.find(".vetedge-dashboard-composition"), payload.revenue_composition));
							wrapper.find(".vetedge-dashboard-composition-section").show();
						} else {
							wrapper.find(".vetedge-dashboard-composition-section").hide();
						}

						// Render Financial Health Indicators
						if (payload.health_indicators && payload.health_indicators.length) {
							wrapper.find(".vetedge-dashboard-health").html(renderHealthIndicators(payload.health_indicators));
							wrapper.find(".vetedge-dashboard-health-section").show();
						} else {
							wrapper.find(".vetedge-dashboard-health-section").hide();
						}

						// Render Outstanding Breakdowns & Rankings
						if (payload.outstanding_breakdowns) {
							wrapper.find(".vetedge-dashboard-outstanding").html(renderOutstandingBreakdowns(payload.outstanding_breakdowns));
							wrapper.find(".vetedge-dashboard-outstanding-section").show();
						} else {
							wrapper.find(".vetedge-dashboard-outstanding-section").hide();
						}

						// Render Charts
						renderCharts(wrapper, payload.charts || []);
						if (typeof afterRefresh === "function") afterRefresh();
					},
				});
			}

			refresh();
		},
	};
})();
