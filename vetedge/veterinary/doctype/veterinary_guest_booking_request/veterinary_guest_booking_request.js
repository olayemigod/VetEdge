frappe.ui.form.on("Veterinary Guest Booking Request", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		if (frm.doc.linked_customer) {
			frm.add_custom_button(__("Open Customer"), () => {
				frappe.set_route("Form", "Customer", frm.doc.linked_customer);
			}, __("Open"));
		}

		if (frm.doc.linked_patient) {
			frm.add_custom_button(__("Open Patient"), () => {
				frappe.set_route("Form", "Veterinary Patient", frm.doc.linked_patient);
			}, __("Open"));
		}

		if (frm.doc.registration_invoice) {
			frm.add_custom_button(__("Open Registration Invoice"), () => {
				vetedgeInvoiceSummary.open(frm.doc.registration_invoice);
			}, __("Open"));
		}

		if (frm.doc.linked_appointment) {
			frm.add_custom_button(__("Open Appointment"), () => {
				frappe.set_route("Form", "Veterinary Appointment", frm.doc.linked_appointment);
			}, __("Open"));
		}

		if (["Converted", "Cancelled"].includes(frm.doc.status)) {
			return;
		}

		if (!frm.doc.linked_patient) {
			frm.add_custom_button(__("Confirm Registration"), () => {
				frappe.call({
					method: "vetedge.services.guest_booking.confirm_guest_registration",
					args: {
						booking_request: frm.doc.name,
					},
					freeze: true,
					freeze_message: __("Confirming registration..."),
					callback() {
						frm.reload_doc();
					},
				});
			}, __("Actions"));

			if (frm.doc.linked_appointment) {
				frm.dashboard.add_comment(
					__("Appointment request is waiting for registration confirmation."),
					"yellow",
					true
				);
			}
		} else if (frm.doc.appointment_requested && !frm.doc.linked_appointment) {
			frm.add_custom_button(__("Create Appointment"), () => {
				frappe.call({
					method: "vetedge.services.guest_booking.create_appointment_from_booking_request",
					args: {
						booking_request: frm.doc.name,
					},
					freeze: true,
					freeze_message: __("Creating appointment..."),
					callback(result) {
						if (!result.message) {
							return;
						}

						frm.reload_doc();
						frappe.set_route("Form", "Veterinary Appointment", result.message.name);
					},
				});
			}, __("Actions"));
		}
	},
});
