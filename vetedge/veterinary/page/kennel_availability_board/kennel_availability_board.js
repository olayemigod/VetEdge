frappe.pages["kennel-availability-board"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Kennel Availability Board"),
		single_column: true,
	});

	const view = new VetEdgeKennelAvailabilityBoard(page);
	view.setup();
};

class VetEdgeKennelAvailabilityBoard {
	constructor(page) {
		this.page = page;
		this.body = $(`
			<div class="vetedge-kennel-availability-board">
				<div class="vetedge-kennel-board-summary row mb-4"></div>
				<div class="frappe-card p-3">
					<div class="mb-3">
						<h4 class="mb-1">${__("Kennel Status Board")}</h4>
						<p class="text-muted mb-0">${__("See kennel capacity, occupancy, reservation pressure, and expected release dates for the selected date range.")}</p>
					</div>
					<div class="vetedge-kennel-board-table"></div>
				</div>
			</div>
		`).appendTo(page.body);
	}

	setup() {
		this.branch = this.page.add_field({
			fieldname: "branch",
			label: __("Branch"),
			fieldtype: "Link",
			options: "Branch",
			change: () => this.refresh(),
		});
		this.fromDate = this.page.add_field({
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.route_options?.from_date || frappe.datetime.now_date(),
			change: () => this.refresh(),
		});
		this.toDate = this.page.add_field({
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.route_options?.to_date || frappe.datetime.add_days(frappe.datetime.now_date(), 7),
			change: () => this.refresh(),
		});
		this.kennel = this.page.add_field({
			fieldname: "kennel",
			label: __("Kennel"),
			fieldtype: "Link",
			options: "Kennel",
			change: () => this.refresh(),
		});
		this.status = this.page.add_field({
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Available", "Reserved", "Occupied", "Full", "Out of Service / Inactive"].join("\n"),
			change: () => this.refresh(),
		});
		if (frappe.route_options?.branch) {
			this.branch.set_value(frappe.route_options.branch);
		}
		if (frappe.route_options?.kennel) {
			this.kennel.set_value(frappe.route_options.kennel);
		}
		this.page.set_primary_action(__("Refresh"), () => this.refresh());
		this.refresh();
	}

	getFilters() {
		return {
			branch: this.branch.get_value(),
			from_date: this.fromDate.get_value(),
			to_date: this.toDate.get_value(),
			kennel: this.kennel.get_value(),
			status: this.status.get_value(),
		};
	}

	refresh() {
		frappe.call({
			method: "vetedge.services.boarding.get_kennel_availability_board_view",
			args: this.getFilters(),
			freeze: true,
			freeze_message: __("Loading kennel availability board..."),
			callback: (result) => this.render(result.message || {}),
		});
	}

	render(data) {
		this.renderCards(data.cards || []);
		this.renderTable(data.rows || [], data.filters || {});
	}

	renderCards(cards) {
		const summary = this.body.find('.vetedge-kennel-board-summary').empty();
		(cards || []).forEach((card) => {
			$(`
				<div class="col-md-2 col-sm-6 mb-3">
					<div class="frappe-card p-3 h-100">
						<div class="text-muted small mb-2">${escapeHtml(card.label)}</div>
						<div class="h3 mb-0">${escapeHtml(card.value)}</div>
					</div>
				</div>
			`).appendTo(summary);
		});
	}

	renderTable(rows, filters) {
		const wrapper = this.body.find('.vetedge-kennel-board-table').empty();
		if (!rows.length) {
			wrapper.html(`<div class="text-muted">${__("No kennels match the selected filters.")}</div>`);
			return;
		}
		const rangeLabel = `${frappe.datetime.str_to_user(filters.from_date || frappe.datetime.now_date())} - ${frappe.datetime.str_to_user(filters.to_date || filters.from_date || frappe.datetime.now_date())}`;
		wrapper.html(`
			<div class="text-muted small mb-3">${__("Date Range")}: ${escapeHtml(rangeLabel)}</div>
			<div class="table-responsive">
				<table class="table table-bordered table-hover table-sm">
					<thead>
						<tr>
							<th>${__("Kennel")}</th>
							<th>${__("Branch")}</th>
							<th>${__("Capacity")}</th>
							<th>${__("Current Occupancy")}</th>
							<th>${__("Available Slots")}</th>
							<th>${__("Status")}</th>
							<th>${__("Active Booking / Stay")}</th>
							<th>${__("Expected Check-Out Date")}</th>
						</tr>
					</thead>
					<tbody>
						${rows.map((row) => `
							<tr class="vetedge-kennel-board-row" data-kennel="${escapeHtml(row.kennel)}" style="cursor: pointer;">
								<td>
									<div style="font-weight: 600;">${escapeHtml(row.kennel_name || row.kennel)}</div>
									<div class="text-muted small">${escapeHtml(row.kennel)}</div>
								</td>
								<td>${escapeHtml(row.branch || "")}</td>
								<td>${escapeHtml(row.capacity)}</td>
								<td>${escapeHtml(row.current_occupancy)}</td>
								<td>${escapeHtml(row.available_slots)}</td>
								<td><span class="indicator-pill ${statusPill(row.status)}">${escapeHtml(__(row.status || "Unknown"))}</span></td>
								<td>${escapeHtml(row.active_reference || __("None"))}</td>
								<td>${row.expected_check_out_date ? escapeHtml(frappe.datetime.str_to_user(row.expected_check_out_date)) : __("Not scheduled")}</td>
							</tr>
						`).join('')}
					</tbody>
				</table>
			</div>
		`);
		wrapper.find('.vetedge-kennel-board-row').on('click', (event) => {
			const kennel = $(event.currentTarget).attr('data-kennel');
			if (kennel) {
				frappe.set_route('Form', 'Kennel', kennel);
			}
		});
	}
}

function statusPill(status) {
	return {
		Available: 'green',
		Reserved: 'orange',
		Occupied: 'blue',
		Full: 'red',
		'Out of Service / Inactive': 'gray',
	}[status] || 'gray';
}

function escapeHtml(value) {
	if (value === undefined || value === null) {
		return '';
	}
	return frappe.utils.escape_html(String(value));
}
