frappe.ui.form.on("Pet Boarding Stay", {
	async booking(frm) {
		if (!frm.doc.booking) {
			return;
		}

		const response = await frappe.db.get_value(
			"Pet Boarding Booking",
			frm.doc.booking,
			["patient", "primary_owner", "service_branch"]
		);
		const booking = response?.message || {};
		await frm.set_value({
			patient: booking.patient || null,
			primary_owner: booking.primary_owner || null,
			service_branch: booking.service_branch || null,
		});
	},

	refresh(frm) {
		if (frm.is_new()) {
			return;
		}
		addBoardingCareRecordActions(frm);
	},
});

function addBoardingCareRecordActions(frm) {
	frm.add_custom_button(__("Add Care Record"), () => {
		showNewBoardingCareRecordDialog(frm);
	}, __("Care Records"));

	frm.add_custom_button(__("View Care Records"), () => {
		showBoardingCareRecordsDialog(frm);
	}, __("Care Records"));
}

function showNewBoardingCareRecordDialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("New Boarding Care Record"),
		fields: [
			{ fieldtype: "Datetime", fieldname: "care_datetime", label: __("Care Datetime"), default: frappe.datetime.now_datetime(), reqd: 1 },
			{ fieldtype: "Select", fieldname: "care_type", label: __("Care Type"), options: `Routine Check\nFeeding\nHydration\nWalk / Exercise\nElimination\nGrooming Check\nComfort / Behavior\nCheck Out Prep`, reqd: 1 },
			{ fieldtype: "Select", fieldname: "record_status", label: __("Record Status"), options: `Completed\nSkipped\nNeeds Attention`, default: "Completed", reqd: 1 },
			{ fieldtype: "Section Break", fieldname: "structured_section", label: __("Structured Care Data") },
			{ fieldtype: "Select", fieldname: "feeding_status", label: __("Feeding Status"), options: `\nNot Applicable\nOffered\nPartially Eaten\nFully Eaten\nDeclined` },
			{ fieldtype: "Select", fieldname: "appetite_status", label: __("Appetite Status"), options: `\nNot Assessed\nPoor\nFair\nGood\nExcellent` },
			{ fieldtype: "Percent", fieldname: "food_portion_percent", label: __("Food Portion Consumed (%)") },
			{ fieldtype: "Float", fieldname: "water_intake_ml", label: __("Water Intake (ml)") },
			{ fieldtype: "Column Break" },
			{ fieldtype: "Select", fieldname: "walk_status", label: __("Walk Status"), options: `\nNot Applicable\nCompleted\nSkipped\nNeeds Attention` },
			{ fieldtype: "Int", fieldname: "walk_duration_minutes", label: __("Walk Duration (Minutes)") },
			{ fieldtype: "Select", fieldname: "elimination_status", label: __("Elimination Status"), options: `\nNot Observed\nNormal\nUrinated Only\nDefecated Only\nUrinated and Defecated\nNeeds Attention` },
			{ fieldtype: "Select", fieldname: "mood_status", label: __("Mood Status"), options: `\nCalm\nPlayful\nAnxious\nRestless\nAggressive\nLethargic\nNeeds Attention` },
			{ fieldtype: "Select", fieldname: "grooming_check_status", label: __("Grooming Check Status"), options: `\nNot Applicable\nClean\nNeeds Cleaning\nNeeds Attention` },
			{ fieldtype: "Section Break", fieldname: "notes_section", label: __("Notes") },
			{ fieldtype: "Small Text", fieldname: "notes", label: __("Notes") },
		],
		primary_action_label: __("Save Care Record"),
		primary_action(values) {
			frappe.call({
				method: "frappe.client.insert",
				args: {
					doc: {
						doctype: "Pet Boarding Care Record",
						stay: frm.doc.name,
						booking: frm.doc.booking,
						patient: frm.doc.patient,
						primary_owner: frm.doc.primary_owner,
						service_branch: frm.doc.service_branch,
						kennel: frm.doc.kennel,
						...values,
					},
				},
				freeze: true,
				freeze_message: __("Saving care record..."),
				callback(response) {
					if (!response?.message?.name) {
						return;
					}
					dialog.hide();
					frappe.show_alert({ message: __("Boarding care record saved"), indicator: "green" });
				},
			});
		},
	});

	dialog.show();
}

function showBoardingCareRecordsDialog(frm) {
	frappe.call({
		method: "frappe.client.get_list",
		args: {
			doctype: "Pet Boarding Care Record",
			filters: { stay: frm.doc.name },
			fields: [
				"name",
				"care_datetime",
				"care_type",
				"record_status",
				"feeding_status",
				"appetite_status",
				"food_portion_percent",
				"water_intake_ml",
				"walk_status",
				"walk_duration_minutes",
				"elimination_status",
				"mood_status",
				"grooming_check_status",
				"recorded_by",
				"notes",
			],
			order_by: "care_datetime desc",
			limit_page_length: 50,
		},
		freeze: true,
		freeze_message: __("Loading care records..."),
		callback(response) {
			const rows = response?.message || [];
			const dialog = new frappe.ui.Dialog({
				title: __("Boarding Care Records"),
				fields: [{ fieldname: "history_html", fieldtype: "HTML" }],
				primary_action_label: __("Close"),
				primary_action() {
					dialog.hide();
				},
			});

			dialog.fields_dict.history_html.$wrapper.html(renderBoardingCareRecordHistory(rows));
			dialog.fields_dict.history_html.$wrapper.find("[data-care-record-name]").on("click", function () {
				const recordName = $(this).attr("data-care-record-name");
				dialog.hide();
				frappe.set_route("Form", "Pet Boarding Care Record", recordName);
			});
			dialog.show();
		},
	});
}

function renderBoardingCareRecordHistory(rows) {
	if (!rows.length) {
		return `<p class="text-muted mb-0">${__("No care records linked to this stay yet.")}</p>`;
	}

	return `
		<div class="table-responsive">
			<table class="table table-bordered table-sm">
				<thead>
					<tr>
						<th>${__("Date / Time")}</th>
						<th>${__("Care Type")}</th>
						<th>${__("Status")}</th>
						<th>${__("Feeding / Water")}</th>
						<th>${__("Walk / Elimination")}</th>
						<th>${__("Mood / Grooming")}</th>
						<th>${__("Recorded By")}</th>
					</tr>
				</thead>
				<tbody>
					${rows
						.map(
							(row) => `
								<tr data-care-record-name="${frappe.utils.escape_html(row.name)}" style="cursor: pointer;">
									<td>${row.care_datetime ? frappe.datetime.str_to_user(row.care_datetime) : __("Unknown")}</td>
									<td>${frappe.utils.escape_html(row.care_type || "")}</td>
									<td>${frappe.utils.escape_html(row.record_status || "")}</td>
									<td>${formatBoardingFeedingSummary(row)}</td>
									<td>${formatBoardingWalkSummary(row)}</td>
									<td>${formatBoardingMoodSummary(row)}</td>
									<td>${frappe.utils.escape_html(row.recorded_by || "")}</td>
								</tr>`
						)
						.join("")}
				</tbody>
			</table>
		</div>
		<div class="text-muted small">${__("Click a care record to open the full form.")}</div>
	`;
}

function formatBoardingFeedingSummary(row) {
	const parts = [];
	if (row.feeding_status && row.feeding_status !== "Not Applicable") {
		parts.push(frappe.utils.escape_html(row.feeding_status));
	}
	if (row.appetite_status && row.appetite_status !== "Not Assessed") {
		parts.push(`${__("Appetite")}: ${frappe.utils.escape_html(row.appetite_status)}`);
	}
	if (row.food_portion_percent != null && row.food_portion_percent !== "") {
		parts.push(`${__("Food")}: ${frappe.utils.escape_html(String(row.food_portion_percent))}%`);
	}
	if (row.water_intake_ml != null && row.water_intake_ml !== "") {
		parts.push(`${__("Water")}: ${frappe.utils.escape_html(String(row.water_intake_ml))} ml`);
	}
	return parts.length ? parts.join(" | ") : __("No feeding data");
}

function formatBoardingWalkSummary(row) {
	const parts = [];
	if (row.walk_status && row.walk_status !== "Not Applicable") {
		parts.push(`${__("Walk")}: ${frappe.utils.escape_html(row.walk_status)}`);
	}
	if (row.walk_duration_minutes != null && row.walk_duration_minutes !== "") {
		parts.push(`${__("Duration")}: ${frappe.utils.escape_html(String(row.walk_duration_minutes))} min`);
	}
	if (row.elimination_status && row.elimination_status !== "Not Observed") {
		parts.push(`${__("Elimination")}: ${frappe.utils.escape_html(row.elimination_status)}`);
	}
	return parts.length ? parts.join(" | ") : __("No walk data");
}

function formatBoardingMoodSummary(row) {
	const parts = [];
	if (row.mood_status) {
		parts.push(`${__("Mood")}: ${frappe.utils.escape_html(row.mood_status)}`);
	}
	if (row.grooming_check_status && row.grooming_check_status !== "Not Applicable") {
		parts.push(`${__("Grooming")}: ${frappe.utils.escape_html(row.grooming_check_status)}`);
	}
	if (row.notes) {
		parts.push(frappe.utils.escape_html(row.notes));
	}
	return parts.length ? parts.join(" | ") : __("No additional notes");
}
