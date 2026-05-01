frappe.pages["kennel-availability"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Kennel Availability"),
		single_column: true,
	});

	const view = new VetEdgeKennelAvailability(page);
	view.setup();
};

class VetEdgeKennelAvailability {
	constructor(page) {
		this.page = page;
		this.body = $(`
			<div class="vetedge-kennel-availability">
				<div class="vetedge-kennel-summary row mb-4"></div>
				<div class="frappe-card p-3">
					<div class="d-flex justify-content-between align-items-center mb-3">
						<div>
							<h4 class="mb-1">${__("Kennel Status Board")}</h4>
							<p class="text-muted mb-0">${__("A live operational view of kennel availability across the selected branch and date.")}</p>
						</div>
					</div>
					<div class="vetedge-kennel-table"></div>
				</div>
			</div>
		`).appendTo(page.body);
	}

	setup() {
		this.snapshot_date = this.page.add_field({
			fieldname: "snapshot_date",
			label: __("Date"),
			fieldtype: "Date",
			default: frappe.datetime.now_date(),
			change: () => this.refresh(),
		});
		this.service_branch = this.page.add_field({
			fieldname: "service_branch",
			label: __("Branch"),
			fieldtype: "Link",
			options: "Branch",
			change: () => this.refresh(),
		});
		this.page.set_primary_action(__("Refresh"), () => this.refresh());
		this.refresh();
	}

	get_filters() {
		return {
			snapshot_date: this.snapshot_date.get_value(),
			service_branch: this.service_branch.get_value(),
		};
	}

	refresh() {
		frappe.call({
			method: "vetedge.services.boarding.get_kennel_availability_dashboard_view",
			args: this.get_filters(),
			freeze: true,
			freeze_message: __("Loading kennel availability..."),
			callback: (result) => this.render(result.message || {}),
		});
	}

	render(data) {
		this.render_summary(data.cards || []);
		this.render_table(data.rows || [], data.snapshot_date);
	}

	render_summary(cards) {
		const summary = this.body.find(".vetedge-kennel-summary").empty();
		(cards || []).forEach((card) => {
			$(`
				<div class="col-md-2 col-sm-6 mb-3">
					<div class="frappe-card p-3 h-100">
						<div class="text-muted small mb-2">${escape_html(card.label)}</div>
						<div class="h3 mb-0">${escape_html(card.value)}</div>
					</div>
				</div>
			`).appendTo(summary);
		});
	}

	render_table(rows, snapshotDate) {
		const wrapper = this.body.find(".vetedge-kennel-table").empty();
		if (!rows.length) {
			wrapper.html(`<div class="text-muted">${__("No kennels found for this filter.")}</div>`);
			return;
		}

		const html = `
			<div class="text-muted small mb-3">${__("Snapshot Date")}: ${escape_html(frappe.datetime.str_to_user(snapshotDate || frappe.datetime.now_date()))}</div>
			<div class="table-responsive">
				<table class="table table-bordered table-hover table-sm">
					<thead>
						<tr>
							<th>${__("Kennel")}</th>
							<th>${__("Branch")}</th>
							<th>${__("Status")}</th>
							<th>${__("Capacity")}</th>
							<th>${__("Occupied")}</th>
							<th>${__("Available")}</th>
							<th>${__("Reserved")}</th>
							<th>${__("Active Stays")}</th>
							<th>${__("Occupancy")}</th>
							<th>${__("Next Expected Release")}</th>
						</tr>
					</thead>
					<tbody>
						${rows.map((row) => `
							<tr class="vetedge-kennel-row" data-kennel="${escape_html(row.kennel)}" style="cursor: pointer;">
								<td>
									<div style="font-weight: 600;">${escape_html(row.kennel_name || row.kennel)}</div>
									<div class="text-muted small">${escape_html(row.kennel)}</div>
								</td>
								<td>${escape_html(row.service_branch || "")}</td>
								<td><span class="indicator-pill ${statusPill(row.availability_status)}">${escape_html(__(row.availability_status || "Unknown"))}</span></td>
								<td>${escape_html(row.capacity)}</td>
								<td>${escape_html(row.occupied_slots)}</td>
								<td>${escape_html(row.available_slots)}</td>
								<td>${escape_html(row.reserved_bookings)}</td>
								<td>${escape_html(row.active_stays)}</td>
								<td>${escape_html(String(row.occupancy_percent ?? 0))}%</td>
								<td>${row.next_expected_release_date ? escape_html(frappe.datetime.str_to_user(row.next_expected_release_date)) : __("Not scheduled")}</td>
							</tr>
						`).join("")}
					</tbody>
				</table>
			</div>
		`;
		wrapper.html(html);
		wrapper.find('.vetedge-kennel-row').on('click', (event) => {
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
		Limited: 'orange',
		Full: 'red',
		Inactive: 'gray',
	}[status] || 'gray';
}

function escape_html(value) {
	if (value === undefined || value === null) {
		return "";
	}
	return frappe.utils.escape_html(String(value));
}
