frappe.pages["veterinary-appointment-queue"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("VetEdge Appointment Queue"),
		single_column: true,
	});

	const view = new VetEdgeAppointmentQueue(page);
	view.setup();
};

class VetEdgeAppointmentQueue {
	constructor(page) {
		this.page = page;
		this.body = $(`
			<div class="vetedge-appointment-queue">
				<div class="vetedge-queue-sections"></div>
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
		this.practitioner = this.page.add_field({
			fieldname: "practitioner",
			label: __("Practitioner"),
			fieldtype: "Link",
			options: "User",
			change: () => this.refresh(),
		});
		this.status = this.page.add_field({
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: [
				"",
				"Owner Requested",
				"Awaiting Registration",
				"Scheduled",
				"Confirmed",
				"Checked In",
				"In Consultation",
				"Completed",
				"Rescheduled",
				"Cancelled",
				"No Show",
			].join("\n"),
			change: () => this.refresh(),
		});
		this.page.set_primary_action(__("Refresh"), () => this.refresh());
		this.refresh();
	}

	refresh() {
		frappe.call({
			method: "vetedge.services.appointment_flow.get_appointment_queue",
			args: {
				branch: this.branch.get_value(),
				practitioner: this.practitioner.get_value(),
				status: this.status.get_value(),
			},
			freeze: true,
			freeze_message: __("Loading appointment queue..."),
			callback: (result) => {
				this.render(result.message || {});
			},
		});
	}

	render(data) {
		const sections = this.body.find(".vetedge-queue-sections").empty();
		this.render_section(sections, __("Today's Appointments"), data.today || []);
		this.render_section(sections, __("Tomorrow's Appointments"), data.tomorrow || []);
		this.render_section(sections, __("Future Appointments"), data.future || []);
	}

	render_section(parent, title, rows) {
		const section = $(`
			<div class="frappe-card p-3 mb-4">
				<div class="d-flex justify-content-between align-items-center mb-2">
					<h4 class="mb-0">${title}</h4>
					<span class="text-muted">${rows.length}</span>
				</div>
				<div class="table-responsive"></div>
			</div>
		`).appendTo(parent);

		if (!rows.length) {
			section.find(".table-responsive").html(`<p class="text-muted mb-0">${__("No appointments.")}</p>`);
			return;
		}

		const body = rows
			.map((row) => {
				const route = `/app/veterinary-appointment/${encodeURIComponent(row.name)}`;
				return `
					<tr>
						<td><a href="${route}">${escape_html(row.appointment_title || row.patient)}</a></td>
						<td>${escape_html(format_datetime(row.appointment_datetime))}</td>
						<td>${escape_html(row.practitioner_name || row.practitioner || "")}</td>
						<td>${escape_html(row.branch)}</td>
						<td>${status_badge(row.status)}</td>
					</tr>
				`;
			})
			.join("");

		section.find(".table-responsive").html(`
			<table class="table table-bordered table-sm">
				<thead>
					<tr>
						<th>${__("Patient")}</th>
						<th>${__("Time")}</th>
						<th>${__("Practitioner")}</th>
						<th>${__("Branch")}</th>
						<th>${__("Status")}</th>
					</tr>
				</thead>
				<tbody>${body}</tbody>
			</table>
		`);
	}
}

function format_datetime(value) {
	return value ? frappe.datetime.str_to_user(value) : "";
}

function escape_html(value) {
	if (value === undefined || value === null) {
		return "";
	}
	return frappe.utils.escape_html(String(value));
}

function status_badge(status) {
	const value = escape_html(status || "");
	const color = appointment_status_color(status);
	return `<span class="indicator-pill ${color}">${value}</span>`;
}

function appointment_status_color(status) {
	return (
		{
			"Awaiting Registration": "gray",
			"Owner Requested": "orange",
			Scheduled: "blue",
			Confirmed: "green",
			"Checked In": "yellow",
			"In Consultation": "purple",
			Completed: "green",
			Rescheduled: "orange",
			Cancelled: "red",
			"No Show": "gray",
		}[status] || "gray"
	);
}
