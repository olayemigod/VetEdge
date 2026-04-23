frappe.pages["veterinary-financial-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Veterinary Financial Dashboard"),
		single_column: true,
	});

	const view = new VetEdgeFinancialDashboard(page);
	view.setup();
};

class VetEdgeFinancialDashboard {
	constructor(page) {
		this.page = page;
		this.body = $(`
			<div class="vetedge-financial-dashboard">
				<div class="vetedge-financial-summary row mb-4"></div>
				<div class="vetedge-financial-charts row"></div>
				<div class="vetedge-financial-shortcuts"></div>
			</div>
		`).appendTo(page.body);
	}

	setup() {
		this.from_date = this.page.add_field({
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			change: () => this.refresh(),
		});
		this.to_date = this.page.add_field({
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.now_date(),
			change: () => this.refresh(),
		});
		this.cost_center = this.page.add_field({
			fieldname: "cost_center",
			label: __("Cost Center"),
			fieldtype: "Link",
			options: "Cost Center",
			change: () => this.refresh(),
		});
		this.page.set_primary_action(__("Refresh"), () => this.refresh());
		this.refresh();
	}

	get_filters() {
		return {
			from_date: this.from_date.get_value(),
			to_date: this.to_date.get_value(),
			cost_center: this.cost_center.get_value(),
		};
	}

	refresh() {
		frappe.call({
			method: "vetedge.services.financial_dashboard.get_financial_dashboard_view",
			args: {
				filters: this.get_filters(),
			},
			freeze: true,
			freeze_message: __("Loading financial dashboard..."),
			callback: (result) => {
				this.render(result.message || {});
			},
		});
	}

	render(data) {
		this.render_summary(data.cards || []);
		this.render_charts(data.charts || []);
		this.render_shortcuts(data.shortcuts || []);
	}

	render_summary(cards) {
		const summary = this.body.find(".vetedge-financial-summary").empty();
		(cards || []).forEach((card) => {
			$(`
				<div class="col-md-2 col-sm-6 mb-3">
					<div class="frappe-card p-3 h-100">
						<div class="text-muted small mb-2">${escape_html(card.label)}</div>
						<div class="h3 mb-0">${escape_html(format_currency_value(card.value, card.currency))}</div>
					</div>
				</div>
			`).appendTo(summary);
		});
	}

	render_charts(charts) {
		const chartArea = this.body.find(".vetedge-financial-charts").empty();
		(charts || []).forEach((chart, index) => {
			const colClass = index === 0 ? "col-12" : "col-12 col-lg-6";
			const card = $(`
				<div class="${colClass} mb-4">
					<div class="frappe-card p-3">
						<h4 class="mb-3">${escape_html(chart.label)}</h4>
						<div class="vetedge-financial-chart" data-chart="${escape_html(chart.key)}"></div>
					</div>
				</div>
			`).appendTo(chartArea);
			this.render_chart(card.find(".vetedge-financial-chart")[0], chart);
		});
	}

	render_chart(element, chart) {
		if (!chart?.data?.labels?.length) {
			$(element).html(`<p class="text-muted mb-0">${__("No data available for this range.")}</p>`);
			return;
		}

		new frappe.Chart(element, {
			data: chart.data,
			type: chart.type || "bar",
			height: 260,
			lineOptions: { hideDots: 0 },
		});
	}

	render_shortcuts(shortcuts) {
		const shortcutArea = this.body.find(".vetedge-financial-shortcuts").empty();
		const wrapper = $(`
			<div class="frappe-card p-3 mb-4">
				<h4 class="mb-3">${__("Financial Workbench")}</h4>
				<p class="text-muted mb-3">${__("Quick links to the main finance actions and reports used from this dashboard.")}</p>
				<div class="row"></div>
			</div>
		`).appendTo(shortcutArea);

		(shortcuts || []).forEach((shortcut) => {
			const route = build_route(shortcut);
			$(`
				<div class="col-12 col-md-6 col-xl-3 mb-3">
					<a class="frappe-card p-3 d-block text-decoration-none" href="${route}">
						<div class="text-muted small mb-2">${__("Open")}</div>
						<div class="h5 mb-0">${escape_html(shortcut.label)}</div>
					</a>
				</div>
			`).appendTo(wrapper.find(".row"));
		});
	}
}

function build_route(shortcut) {
	if (shortcut.route) {
		return frappe.utils.generate_route(shortcut.route);
	}
	return "#";
}

function format_currency_value(value, currency) {
	return format_currency(value || 0, currency || frappe.defaults.get_default("currency"));
}

function escape_html(value) {
	if (value === undefined || value === null) {
		return "";
	}
	return frappe.utils.escape_html(String(value));
}
