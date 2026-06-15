frappe.ui.form.on("Veterinary Missed Appointment", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		add_missed_appointment_actions(frm);
	},
});

function add_missed_appointment_actions(frm) {
	if (frm.doc.appointment) {
		frm.add_custom_button(__("Open Appointment"), () => {
			frappe.set_route("Form", "Veterinary Appointment", frm.doc.appointment);
		}, __("Missed Appointment"));
	}

	if (frm.doc.resolved) {
		frm.add_custom_button(__("Reopen"), () => {
			prompt_note({
				title: __("Reopen Missed Appointment"),
				primary_label: __("Reopen"),
				fieldname: "note",
				callback(values) {
					call_missed_action(frm, "reopen_missed_appointment", values, __("Missed appointment reopened"));
				},
			});
		}, __("Missed Appointment"));
		return;
	}

	frm.add_custom_button(__("Mark Contacted"), () => {
		prompt_note({
			title: __("Mark Contacted"),
			primary_label: __("Mark Contacted"),
			fieldname: "note",
			callback(values) {
				call_missed_action(frm, "mark_missed_appointment_contacted", values, __("Missed appointment marked contacted"));
			},
		});
	}, __("Missed Appointment"));

	frm.add_custom_button(__("Reschedule Appointment"), () => {
		const dialog = new frappe.ui.Dialog({
			title: __("Reschedule Appointment"),
			fields: [
				{
					fieldname: "new_date",
					fieldtype: "Date",
					label: __("New Date"),
					reqd: 1,
				},
				{
					fieldname: "new_time",
					fieldtype: "Time",
					label: __("New Time"),
				},
				{
					fieldname: "note",
					fieldtype: "Small Text",
					label: __("Note"),
				},
			],
			primary_action_label: __("Reschedule"),
			primary_action(values) {
				dialog.hide();
				call_missed_action(frm, "reschedule_missed_appointment", values, __("Appointment rescheduled"));
			},
		});
		dialog.show();
	}, __("Missed Appointment"));

	frm.add_custom_button(__("Cancel Appointment"), () => {
		prompt_note({
			title: __("Cancel Appointment"),
			primary_label: __("Cancel Appointment"),
			fieldname: "note",
			callback(values) {
				call_missed_action(frm, "cancel_missed_appointment", values, __("Appointment cancelled"));
			},
		});
	}, __("Missed Appointment"));

	frm.add_custom_button(__("Resolve"), () => {
		prompt_note({
			title: __("Resolve Missed Appointment"),
			primary_label: __("Resolve"),
			fieldname: "resolution_note",
			callback(values) {
				call_missed_action(frm, "resolve_missed_appointment", values, __("Missed appointment resolved"));
			},
		});
	}, __("Missed Appointment"));
}

function prompt_note({ title, primary_label, fieldname, callback }) {
	const dialog = new frappe.ui.Dialog({
		title,
		fields: [
			{
				fieldname,
				fieldtype: "Small Text",
				label: __("Note"),
			},
		],
		primary_action_label: primary_label,
		primary_action(values) {
			dialog.hide();
			callback(values || {});
		},
	});
	dialog.show();
}

function call_missed_action(frm, method_name, values, success_message) {
	frappe.call({
		method: `vetedge.services.appointment_flow.${method_name}`,
		args: {
			missed_appointment: frm.doc.name,
			...(values || {}),
		},
		freeze: true,
		freeze_message: __("Updating missed appointment..."),
		callback() {
			frappe.show_alert({
				message: success_message,
				indicator: "green",
			});
			frm.reload_doc();
		},
	});
}
