frappe.ui.form.on("Pet Boarding Booking", {
	async patient(frm) {
		if (!frm.doc.patient) {
			await frm.set_value("primary_owner", null);
			return;
		}
		const response = await frappe.db.get_value("Veterinary Patient", frm.doc.patient, ["primary_owner", "default_branch"]);
		const patient = response?.message || {};
		await frm.set_value("primary_owner", patient.primary_owner || null);
		if (!frm.doc.service_branch && patient.default_branch) {
			await frm.set_value("service_branch", patient.default_branch);
		}
		if (!frm.doc.billing_item) {
			frappe.call({
				method: "frappe.client.get_single_value",
				args: { doctype: "Veterinary Settings", field: "default_boarding_billing_item" },
				callback: async (result) => {
					if (result.message && !frm.doc.billing_item) {
						await frm.set_value("billing_item", result.message);
					}
				},
			});
		}
		if (!frm.doc.daily_rate) {
			frappe.call({
				method: "frappe.client.get_single_value",
				args: { doctype: "Veterinary Settings", field: "default_boarding_daily_rate" },
				callback: async (result) => {
					if (result.message && !frm.doc.daily_rate) {
						await frm.set_value("daily_rate", result.message);
					}
				},
			});
		}
	},

	setup(frm) {
		frm.set_query("kennel", () => ({
			filters: frm.doc.service_branch ? { branch: frm.doc.service_branch, is_active: 1 } : { is_active: 1 },
		}));
	},

	refresh(frm) {
		if (frm.is_new()) {
			return;
		}
		addBoardingBookingActions(frm);
	},
});

function addBoardingBookingActions(frm) {
	if (frm.doc.status === "Draft") {
		frm.add_custom_button(__("Reserve"), () => transitionBoardingBooking(frm, "vetedge.services.boarding.reserve_boarding_booking", __("Reserving boarding booking...")), __("Workflow"));
	}
	if (frm.doc.status === "Reserved") {
		frm.add_custom_button(__("Check In"), () => transitionBoardingBooking(frm, "vetedge.services.boarding.check_in_boarding_booking", __("Checking in boarding booking...")), __("Workflow"));
	}
	if (frm.doc.status === "Checked In") {
		frm.add_custom_button(__("Check Out"), () => transitionBoardingBooking(frm, "vetedge.services.boarding.check_out_boarding_booking", __("Checking out boarding booking...")), __("Workflow"));
	}
	if (["Draft", "Reserved"].includes(frm.doc.status)) {
		frm.add_custom_button(__("Cancel"), () => transitionBoardingBooking(frm, "vetedge.services.boarding.cancel_boarding_booking", __("Cancelling boarding booking...")), __("Workflow"));
	}
	frm.add_custom_button(__("Billing / Payment"), () => {
		if (window.vetedgeBillingModal?.open) {
			window.vetedgeBillingModal.open(frm);
			return;
		}
		frappe.msgprint(__("Billing modal helper is not available. Please refresh the page."));
	}, __("Billing"));
	frm.add_custom_button(__("View Availability Board"), () => {
		frappe.route_options = {
			branch: frm.doc.service_branch || undefined,
			from_date: frm.doc.check_in_date || frappe.datetime.now_date(),
			to_date: frm.doc.expected_check_out_date || frm.doc.check_in_date || frappe.datetime.add_days(frappe.datetime.now_date(), 7),
			kennel: frm.doc.kennel || undefined,
		};
		frappe.set_route("kennel-availability-board");
	}, __("Boarding"));

	if (frm.doc.linked_stay) {
		frm.add_custom_button(__("View Stay"), () => {
			frappe.set_route("Form", "Pet Boarding Stay", frm.doc.linked_stay);
		}, __("Boarding"));
	}
	const invoices = getBoardingInvoices(frm);
	if (invoices.length) {
		frm.add_custom_button(__("View Invoices"), () => {
			if (window.vetedgeInvoiceSummary?.openHistory) {
				window.vetedgeInvoiceSummary.openHistory(invoices);
				return;
			}
			frappe.msgprint(__("Invoice summary helper is not available. Please refresh the page."));
		}, __("Billing"));
		frm.add_custom_button(__("View Invoice"), () => {
			if (window.vetedgeInvoiceSummary?.open) {
				window.vetedgeInvoiceSummary.open(invoices[invoices.length - 1].name);
				return;
			}
			frappe.msgprint(__("Invoice summary helper is not available. Please refresh the page."));
		}, __("Billing"));
	}
}

function getBoardingInvoices(frm) {
	const rows = (frm.doc.booking_invoices || []).map((row) => ({
		name: row.sales_invoice,
		status: row.invoice_status,
		posting_date: row.posting_date,
		currency: row.currency,
		grand_total: row.grand_total,
		outstanding_amount: row.outstanding_amount,
	})).filter((row) => row.name);

	if (!rows.length && frm.doc.linked_invoice) {
		rows.push({ name: frm.doc.linked_invoice, status: frm.doc.payment_status });
	}

	return rows;
}

function transitionBoardingBooking(frm, method, freezeMessage) {
	frappe.call({
		method,
		args: { booking: frm.doc.name },
		freeze: true,
		freeze_message: freezeMessage,
		callback() { frm.reload_doc(); },
	});
}
