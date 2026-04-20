frappe.pages["veterinary-medical-history"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Veterinary Medical History"),
		single_column: true,
	});

	const view = new VetEdgeMedicalHistory(page);
	view.setup();
};

class VetEdgeMedicalHistory {
	constructor(page) {
		this.page = page;
		this.body = $(`
			<div class="vetedge-medical-history">
				<div class="vetedge-history-summary"></div>
				<div class="vetedge-history-charts"></div>
				<div class="vetedge-history-sections"></div>
			</div>
		`).appendTo(page.body);
	}

	setup() {
		this.patient = this.page.add_field({
			fieldname: "patient",
			label: __("Patient"),
			fieldtype: "Link",
			options: "Veterinary Patient",
			reqd: 1,
			change: () => this.refresh(),
		});
		this.from_date = this.page.add_field({
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -90),
			change: () => this.refresh(),
		});
		this.to_date = this.page.add_field({
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			change: () => this.refresh(),
		});
		this.page.set_primary_action(__("Refresh"), () => this.refresh());

		const route_patient = frappe.route_options?.patient;
		if (route_patient) {
			this.patient.set_value(route_patient);
			frappe.route_options = null;
		}

		this.render_empty_state();
		if (this.patient.get_value()) {
			this.refresh();
		}
	}

	refresh() {
		const patient = this.patient.get_value();
		if (!patient) {
			this.render_empty_state();
			return;
		}

		frappe.call({
			method: "vetedge.services.medical_history.get_patient_medical_history_view",
			args: {
				patient,
				from_date: this.from_date.get_value(),
				to_date: this.to_date.get_value(),
			},
			freeze: true,
			freeze_message: __("Loading medical history..."),
			callback: (result) => {
				this.render(result.message || {});
			},
		});
	}

	render(data) {
		this.render_summary(data.summary || {});
		this.render_charts(data.trends || {});
		this.render_sections(data);
	}

	render_empty_state() {
		this.body.find(".vetedge-history-summary").html(`
			<div class="frappe-card p-4">
				<h4>${__("Select a Veterinary Patient")}</h4>
				<p class="text-muted mb-0">${__("Choose a patient and date range to view consultation history, vitals, diagnoses, symptoms, and planned treatments.")}</p>
			</div>
		`);
		this.body.find(".vetedge-history-charts").empty();
		this.body.find(".vetedge-history-sections").empty();
	}

	render_summary(summary) {
		this.body.find(".vetedge-history-summary").html(`
			<div class="frappe-card p-4 mb-4">
				<h4>${escape_html(summary.patient_name || summary.patient || __("Patient Summary"))}</h4>
				<div class="row">
					${summary_item(__("Species"), summary.species)}
					${summary_item(__("Breed"), summary.breed)}
					${summary_item(__("Owner"), summary.primary_owner)}
					${summary_item(__("Default Branch"), summary.default_branch)}
					${summary_item(__("Latest Consultation"), format_datetime(summary.latest_consultation_date))}
					${summary_item(__("Latest Weight"), summary.latest_weight)}
					${summary_item(__("Latest Temperature"), summary.latest_temperature)}
				</div>
			</div>
		`);
	}

	render_charts(trends) {
		const chart_area = this.body.find(".vetedge-history-charts").empty();
		const chart_specs = [
			["temperature", __("Temperature Trend")],
			["weight", __("Weight Trend")],
			["heart_rate", __("Heart Rate Trend")],
			["respiratory_rate", __("Respiratory Rate Trend")],
		];

		const row = $('<div class="row"></div>').appendTo(chart_area);
		chart_specs.forEach(([fieldname, label]) => {
			const wrapper = $(`
				<div class="col-md-6 mb-4">
					<div class="frappe-card p-3">
						<h5>${label}</h5>
						<div class="vetedge-chart" data-fieldname="${fieldname}"></div>
					</div>
				</div>
			`).appendTo(row);
			this.render_chart(wrapper.find(".vetedge-chart")[0], label, trends[fieldname] || []);
		});
	}

	render_chart(element, label, rows) {
		if (!rows.length) {
			$(element).html(`<p class="text-muted mb-0">${__("No chart data in this range.")}</p>`);
			return;
		}

		new frappe.Chart(element, {
			title: label,
			data: {
				labels: rows.map((row) => frappe.datetime.str_to_user(row.timestamp)),
				datasets: [{ name: label, values: rows.map((row) => row.value) }],
			},
			type: "line",
			height: 220,
			lineOptions: { hideDots: 0 },
		});
	}

	render_sections(data) {
		const sections = this.body.find(".vetedge-history-sections").empty();
		this.render_table(sections, __("Consultation Timeline"), data.consultations || [], [
			[__("Date/Time"), "timestamp", format_datetime],
			[__("Practitioner"), "practitioner"],
			[__("Branch"), "service_branch"],
			[__("Status"), "status"],
			[__("Complaint"), "presenting_complaint"],
			[__("Assessment"), "assessment_notes"],
		]);
		this.render_table(sections, __("Vitals History"), data.vitals || [], [
			[__("Recorded On"), "timestamp", format_datetime],
			[__("Temperature"), "temperature"],
			[__("Weight"), "weight"],
			[__("Heart Rate"), "heart_rate"],
			[__("Respiratory Rate"), "respiratory_rate"],
			[__("Body Condition"), "body_condition_score"],
			[__("Branch"), "service_branch"],
			[__("Consultation"), "consultation"],
		]);
		this.render_table(sections, __("Diagnosis History"), data.diagnoses || [], [
			[__("Date/Time"), "timestamp", format_datetime],
			[__("Diagnosis"), "diagnosis"],
			[__("Type"), "diagnosis_type"],
			[__("Practitioner"), "practitioner"],
			[__("Branch"), "service_branch"],
		]);
		this.render_table(sections, __("Symptom History"), data.symptoms || [], [
			[__("Date/Time"), "timestamp", format_datetime],
			[__("Symptom"), "symptom"],
			[__("Practitioner"), "practitioner"],
			[__("Branch"), "service_branch"],
		]);
		this.render_table(sections, __("Treatment History"), data.treatments || [], [
			[__("Date/Time"), "timestamp", format_datetime],
			[__("Item"), "item"],
			[__("Qty"), "qty"],
			[__("UOM"), "uom"],
			[__("Practitioner"), "practitioner"],
			[__("Branch"), "service_branch"],
		]);
		this.render_placeholders(sections, data.placeholders || {});
	}

	render_table(parent, title, rows, columns) {
		const table = $(`
			<div class="frappe-card p-3 mb-4">
				<h5>${title}</h5>
				<div class="table-responsive"></div>
			</div>
		`).appendTo(parent);

		if (!rows.length) {
			table.find(".table-responsive").html(`<p class="text-muted mb-0">${__("No records in this range.")}</p>`);
			return;
		}

		const header = columns.map(([label]) => `<th>${label}</th>`).join("");
		const body = rows
			.map((row) => {
				const cells = columns
					.map(([, fieldname, formatter]) => {
						const value = formatter ? formatter(row[fieldname]) : row[fieldname];
						return `<td>${escape_html(value)}</td>`;
					})
					.join("");
				return `<tr>${cells}</tr>`;
			})
			.join("");

		table.find(".table-responsive").html(`
			<table class="table table-bordered table-sm">
				<thead><tr>${header}</tr></thead>
				<tbody>${body}</tbody>
			</table>
		`);
	}

	render_placeholders(parent, placeholders) {
		const entries = Object.entries(placeholders);
		if (!entries.length) {
			return;
		}

		parent.append(`
			<div class="frappe-card p-3 mb-4">
				<h5>${__("Future History Sections")}</h5>
				${entries
					.map(([, value]) => `<p class="text-muted mb-1">${escape_html(value)}</p>`)
					.join("")}
			</div>
		`);
	}
}

function summary_item(label, value) {
	return `
		<div class="col-md-3 mb-3">
			<div class="text-muted">${label}</div>
			<div>${escape_html(value)}</div>
		</div>
	`;
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
