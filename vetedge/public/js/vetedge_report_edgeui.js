(function () {
	const reportConfigs = new Map();
	const reportInstances = new WeakMap();

	function getRuntime() {
		return window.EdgeSuiteUI || window.EdgeUI || null;
	}

	function supportsRuntime(runtime) {
		return Boolean(
			runtime
			&& typeof runtime.createEdgeApp === "function"
			&& runtime.Vue
			&& runtime.components?.EdgePageHeader
			&& runtime.components?.EdgeDashboardLayout
			&& runtime.components?.EdgeStatCard
			&& runtime.components?.EdgeStatusBadge
			&& runtime.components?.EdgeEmptyState
		);
	}

	function reportConfig(reportName) {
		return reportConfigs.get(reportName) || null;
	}

	function reportMain(report) {
		return report?.page?.main_section?.length ? report.page.main_section : null;
	}

	function ensureHost(report) {
		const main = reportMain(report);
		if (!main) return null;

		main.closest(".page-container").addClass("vetedge-edgeui-report-page");
		let host = main.children(".vetedge-report-edgeui-host").get(0);
		if (!host) {
			host = document.createElement("div");
			host.className = "vetedge-report-edgeui-host";
			main.prepend(host);
		}
		return host;
	}

	function cardTone(indicator) {
		const value = String(indicator || "neutral").trim().toLowerCase();
		if (["green", "success"].includes(value)) return "success";
		if (["orange", "yellow", "warning"].includes(value)) return "warning";
		if (["red", "danger"].includes(value)) return "danger";
		if (["blue", "purple", "info"].includes(value)) return "info";
		return "neutral";
	}

	function formatValue(card) {
		const value = card?.value;
		if (value === null || value === undefined || value === "") return "—";
		const datatype = card.datatype || card.value_type;
		if (datatype === "Currency" || datatype === "currency") {
			return frappe.format_value
				? frappe.format_value(value, { fieldtype: "Currency" })
				: String(value);
		}
		if (datatype === "Percent" || datatype === "percent") {
			return `${Number(value || 0).toFixed(1).replace(/\.0$/, "")}%`;
		}
		if (datatype === "Float" || datatype === "float") {
			const number = Number(value || 0);
			return Number.isFinite(number) ? number.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(value);
		}
		if (typeof value === "number") return value.toLocaleString();
		return String(value);
	}

	function cardHelper(card) {
		const trend = card?.trend;
		if (trend && trend.direction && trend.direction !== "flat") {
			const arrow = trend.direction === "up" ? "▲" : "▼";
			return `${arrow} ${Number(trend.percentage || 0).toFixed(1).replace(/\.0$/, "")}% vs previous period`;
		}
		if (trend?.direction === "flat") return __("Stable vs previous period");
		return card?.subtitle || card?.helper || "";
	}

	function applyCardAction(report, action) {
		if (!action || action.type !== "report" || !action.target) return;
		frappe.route_options = Object.assign({}, report.get_values?.() || {}, action.filters || {});
		frappe.set_route("query-report", action.target);
	}

	function copyReportLink() {
		const value = window.location.href;
		if (navigator.clipboard?.writeText) {
			navigator.clipboard.writeText(value).then(() => {
				frappe.show_alert({ message: __("Report link copied."), indicator: "green" });
			});
			return;
		}
		const input = document.createElement("input");
		input.value = value;
		document.body.appendChild(input);
		input.select();
		document.execCommand("copy");
		input.remove();
		frappe.show_alert({ message: __("Report link copied."), indicator: "green" });
	}

	function createReportApp(report, reportName, config, runtime, host) {
		const { h, reactive } = runtime.Vue;
		const {
			EdgePageHeader,
			EdgeDashboardLayout,
			EdgeStatCard,
			EdgeStatusBadge,
			EdgeEmptyState,
		} = runtime.components;
		const state = reactive({
			metadata: {},
			cards: [],
			rowCount: 0,
			empty: false,
		});

		const actionButton = (label, className, onClick) => h(
			"button",
			{ type: "button", class: className, onClick },
			label,
		);

		const root = {
			name: "VetEdgeReportEdgeUISurface",
			setup() {
				return () => {
					const metadata = state.metadata || {};
					const capabilities = metadata.capabilities || {};
					const filters = metadata.filter_summary || __("Current report filters");
					const suggestions = metadata.empty_state?.suggestions || [];
					const recommendations = Array.isArray(metadata.recommendations) ? metadata.recommendations : [];
					const health = metadata.health_score || {};
					const statusItems = [
						h(EdgeStatusBadge, {
							label: __("{0} row(s)", [state.rowCount]),
							status: state.rowCount ? "available" : "empty",
							tone: state.rowCount ? "success" : "neutral",
						}),
						h(EdgeStatusBadge, {
							label: filters,
							status: "filters",
							tone: "neutral",
						}),
					];

					if (capabilities.supports_health_score && health.rating) {
						statusItems.push(h(EdgeStatusBadge, {
							label: `${health.rating}: ${Math.round(Number(health.score || 0))}/100`,
							status: health.rating,
							tone: health.severity || "info",
						}));
					}

					const children = [
						h(EdgePageHeader, {
							eyebrow: config.eyebrow || __("Veterinary Report"),
							title: config.title || metadata.title || reportName,
							subtitle: config.subtitle || "",
						}, {
							actions: () => [
								actionButton(__("Refresh"), "edge-button edge-button--primary", () => report.refresh()),
								capabilities.supports_export !== false
									? actionButton(__("Export"), "edge-button", () => report.export_report())
									: null,
								actionButton(__("Print"), "edge-button", () => report.print_report()),
								actionButton(__("Share"), "edge-button", copyReportLink),
							].filter(Boolean),
						}),
						h("div", { class: "vetedge-report-edgeui-context" }, statusItems),
					];

					if (state.cards.length) {
						children.push(h(EdgeDashboardLayout, { minColumnWidth: "12.5rem" }, {
							default: () => state.cards.map((card) => h(
								"div",
								{
									class: ["vetedge-report-edgeui-card", card.action ? "is-clickable" : ""],
									role: card.action ? "button" : undefined,
									tabindex: card.action ? 0 : undefined,
									onClick: () => applyCardAction(report, card.action),
									onKeydown: (event) => {
										if (card.action && ["Enter", " "].includes(event.key)) {
											event.preventDefault();
											applyCardAction(report, card.action);
										}
									},
								},
								[h(EdgeStatCard, {
									label: card.label || card.title || "",
									value: formatValue(card),
									helper: cardHelper(card),
									tone: cardTone(card.indicator || card.tone),
									tooltip: card.tooltip || "",
								})],
							)),
						}));
					}

					if (recommendations.length) {
						children.push(h("section", { class: "vetedge-report-edgeui-recommendations" }, [
							h("div", { class: "vetedge-report-edgeui-section-heading" }, [
								h("p", { class: "edge-eyebrow" }, __("Actionable insight")),
								h("h2", {}, __("Items requiring attention")),
							]),
							h("div", { class: "vetedge-report-edgeui-recommendation-list" }, recommendations.map((item) => h(
								"article",
								{ class: "vetedge-report-edgeui-recommendation" },
								[
									h(EdgeStatusBadge, {
										label: item.severity === "danger" ? __("Urgent") : __("Review"),
										status: item.severity || "warning",
										tone: item.severity || "warning",
									}),
									h("div", {}, [
										h("strong", {}, item.title || __("Recommendation")),
										h("p", {}, item.description || ""),
									]),
								],
							))),
						]));
					}

					if (state.empty) {
						children.push(h("div", { class: "vetedge-report-edgeui-empty" }, [
							h(EdgeEmptyState, {
								title: metadata.empty_state?.message || __("No matching records"),
								description: config.emptyDescription || __("Adjust the filters or date range and refresh the report."),
								icon: metadata.icon || "list",
							}),
							suggestions.length
								? h("ul", { class: "vetedge-report-edgeui-suggestions" }, suggestions.map((item) => h("li", {}, item)))
								: null,
						]));
					}

					return h("section", { class: "vetedge-report-edgeui-surface" }, children);
				};
			},
		};

		const app = runtime.createEdgeApp(root);
		app.mount(host);
		return { app, state, host, reportName };
	}

	function ensureInstance(report, reportName) {
		const existing = reportInstances.get(report);
		if (existing?.reportName === reportName && existing.host?.isConnected) return existing;

		const config = reportConfig(reportName);
		if (!config) return null;
		const host = ensureHost(report);
		if (!host) return null;
		const runtime = getRuntime();
		if (!supportsRuntime(runtime)) return null;

		if (existing?.app) existing.app.unmount();
		const instance = createReportApp(report, reportName, config, runtime, host);
		reportInstances.set(report, instance);
		return instance;
	}

	function attach(report, reportName) {
		if (!reportConfig(reportName)) return false;
		const mount = () => ensureInstance(report, reportName);
		if (supportsRuntime(getRuntime())) {
			mount();
			return true;
		}
		frappe.require("edgeui.bundle.js", mount);
		return true;
	}

	function renderSummary(report, reportName, metadata, cards) {
		if (!reportConfig(reportName)) return false;
		const instance = ensureInstance(report, reportName);
		if (!instance) return false;
		instance.state.metadata = metadata || {};
		instance.state.cards = Array.isArray(cards) ? cards : [];
		instance.state.rowCount = Array.isArray(report.data) ? report.data.length : 0;
		instance.state.empty = instance.state.rowCount === 0;
		return true;
	}

	window.vetedgeReportEdgeUI = {
		register(reportName, config) {
			if (!reportName) return;
			reportConfigs.set(reportName, Object.assign({}, config || {}));
		},
		handles(reportName) {
			return reportConfigs.has(reportName);
		},
		attach,
		renderSummary,
	};
})();
