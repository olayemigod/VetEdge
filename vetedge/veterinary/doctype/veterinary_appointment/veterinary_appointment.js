frappe.ui.form.on("Veterinary Appointment", {
	setup(frm) {
		frm.set_query("patient", () => ({
			filters: {
				status: ["!=", "Deceased"],
			},
		}));
	},

	refresh(frm) {
		set_consultation_link_display(frm);

		if (frm.is_new()) {
			return;
		}

		add_consultation_link_actions(frm);

		if (has_service_consultation(frm)) {
			return;
		}

		if (frm.doc.status === "Awaiting Registration") {
			frm.dashboard.add_comment(
				__("Complete the linked guest registration request before this appointment can be approved."),
				"yellow",
				true
			);
			if (frm.doc.guest_booking_request) {
				frm.add_custom_button(__("Open Registration Request"), () => {
					frappe.set_route("Form", "Veterinary Guest Booking Request", frm.doc.guest_booking_request);
				}, __("Appointment"));
			}
			return;
		}

		if (frm.doc.status === "Owner Requested") {
			frm.add_custom_button(__("Approve Appointment"), () => {
				transition_appointment(frm, "Scheduled");
			}, __("Appointment"));
			frm.add_custom_button(__("Cancel Request"), () => {
				transition_appointment(frm, "Cancelled");
			}, __("Appointment"));
			return;
		}

		if (frm.doc.status === "Scheduled") {
			frm.add_custom_button(__("Confirm Appointment"), () => {
				transition_appointment(frm, "Confirmed");
			}, __("Appointment"));
		}

		if (frm.doc.status === "Confirmed") {
			frm.add_custom_button(__("Check In"), () => {
				transition_appointment(frm, "Checked In");
			}, __("Appointment"));
		}

		if (["Confirmed", "Checked In"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Start Consultation"), () => {
				start_consultation(frm);
			}, __("Appointment"));
		}
	},

	patient(frm) {
		if (!frm.doc.patient) {
			return;
		}

		frappe.db
			.get_value("Veterinary Patient", frm.doc.patient, ["primary_owner", "default_branch"])
			.then((result) => {
				const patient = result?.message || {};
				if (patient.primary_owner) {
					frm.set_value("primary_owner", patient.primary_owner);
				}
				if (!frm.doc.branch && patient.default_branch) {
					frm.set_value("branch", patient.default_branch);
				}
			});
	},

	practitioner(frm) {
		if (!frm.doc.practitioner) {
			frm.set_value("practitioner_name", "");
			return;
		}

		frappe.db.get_value("User", frm.doc.practitioner, "full_name").then((result) => {
			const full_name = result?.message?.full_name;
			frm.set_value("practitioner_name", full_name || frm.doc.practitioner);
		});
	},
});

function set_consultation_link_display(frm) {
	frm.toggle_display("follow_up_reference", Boolean(frm.doc.is_follow_up || frm.doc.follow_up_reference));
	frm.toggle_display("linked_consultation", has_service_consultation(frm));
}

function add_consultation_link_actions(frm) {
	if (has_service_consultation(frm)) {
		frm.add_custom_button(__("Open Service Consultation"), () => {
			frappe.set_route("Form", "Veterinary Consultation", frm.doc.linked_consultation);
		}, __("Consultation"));
	}

	if (frm.doc.follow_up_reference) {
		frm.add_custom_button(__("Open Originating Consultation"), () => {
			frappe.set_route("Form", "Veterinary Consultation", frm.doc.follow_up_reference);
		}, __("Consultation"));
	}
}

function has_service_consultation(frm) {
	return Boolean(
		frm.doc.linked_consultation &&
			frm.doc.linked_consultation !== frm.doc.follow_up_reference
	);
}

function transition_appointment(frm, status) {
	frappe.call({
		method: "vetedge.services.appointment_flow.transition_appointment_status",
		args: {
			appointment: frm.doc.name,
			status,
		},
		freeze: true,
		freeze_message: __("Updating appointment..."),
		callback() {
			frappe.show_alert({
				message: __("Appointment updated"),
				indicator: "green",
			});
			frm.reload_doc();
		},
	});
}

function start_consultation(frm) {
	frappe.call({
		method: "vetedge.services.appointment_flow.create_consultation_from_appointment",
		args: {
			appointment: frm.doc.name,
		},
		freeze: true,
		freeze_message: __("Starting consultation..."),
		callback(result) {
			const consultation = result.message;
			if (!consultation?.name) {
				return;
			}

			frappe.show_alert({
				message: __("Consultation started"),
				indicator: "green",
			});
			frm.reload_doc().then(() => {
				frappe.set_route("Form", "Veterinary Consultation", consultation.name);
			});
		},
	});
}
