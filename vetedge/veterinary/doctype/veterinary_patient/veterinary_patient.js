frappe.ui.form.on("Veterinary Patient", {
	setup(frm) {
		frm.set_query("breed", () => {
			const filters = { disabled: 0 };
			if (frm.doc.species) {
				filters.species = frm.doc.species;
			}
			return { filters };
		});
	},

	refresh(frm) {
		set_registration_status_read_only(frm);
		set_approximate_age(frm);
		if (!frm.is_new()) {
			add_registration_invoice_actions(frm);
			frm.add_custom_button(__("Medical History"), () => {
				frappe.route_options = { patient: frm.doc.name };
				frappe.set_route("veterinary-medical-history");
			});

			if (frm.doc.primary_owner) {
				frm.add_custom_button(__("Create Owner Portal User"), () => {
					create_owner_portal_user(frm);
				}, __("Owner Portal"));
			}
		}
	},

	species(frm) {
		if (frm.doc.breed) {
			frappe.db.get_value("Veterinary Breed", frm.doc.breed, "species").then((result) => {
				const breed_species = result?.message?.species;
				if (breed_species && breed_species !== frm.doc.species) {
					frm.set_value("breed", "");
				}
			});
		}
	},

	date_of_birth(frm) {
		set_approximate_age(frm);
	},
});

function set_registration_status_read_only(frm) {
	frm.set_df_property("registration_status", "read_only", 1);
}

function add_registration_invoice_actions(frm) {
	if (!frm.doc.primary_owner || !frm.doc.default_branch) {
		return;
	}

	frappe.call({
		method: "vetedge.services.registration_billing.is_registration_billing_enabled_for_ui",
		callback(response) {
			if (!response.message) {
				return;
			}

			if (frm.doc.registration_invoice) {
				frm.add_custom_button(__("View Registration Invoice"), () => {
					window.vetedgeInvoiceSummary.open(frm.doc.registration_invoice);
				}, __("Registration Billing"));
				return;
			}

			frm.add_custom_button(__("Create Registration Invoice"), () => {
				frappe.call({
					method: "vetedge.services.registration_billing.create_manual_registration_invoice",
					args: { patient: frm.doc.name },
					freeze: true,
					freeze_message: __("Creating registration invoice..."),
					callback(response) {
						const result = response.message || {};
						if (!result.invoice) {
							return;
						}

						const message = result.created
							? __("Registration invoice {0} created.", [result.invoice])
							: __("Registration invoice {0} is already available.", [result.invoice]);
						frappe.show_alert({ message, indicator: result.created ? "green" : "blue" });
						frm.reload_doc().then(() => {
							window.vetedgeInvoiceSummary.open(result.invoice);
						});
					},
				});
			}, __("Registration Billing"));
		},
		error() {
			return;
		},
	});
}

function set_approximate_age(frm) {
	if (!frm.doc.date_of_birth) {
		frm.set_value("approximate_age", "");
		return;
	}

	const birth_date = frappe.datetime.str_to_obj(frm.doc.date_of_birth);
	const today = frappe.datetime.str_to_obj(frappe.datetime.now_date());
	if (birth_date > today) {
		frm.set_value("approximate_age", "");
		return;
	}

	let years = today.getFullYear() - birth_date.getFullYear();
	let months = today.getMonth() - birth_date.getMonth();
	let days = today.getDate() - birth_date.getDate();

	if (days < 0) {
		months -= 1;
		const previous_month_days = new Date(today.getFullYear(), today.getMonth(), 0).getDate();
		days += previous_month_days;
	}

	if (months < 0) {
		years -= 1;
		months += 12;
	}

	const parts = [];
	if (years) {
		parts.push(format_age_unit(years, __("year")));
	}
	if (months) {
		parts.push(format_age_unit(months, __("month")));
	}
	if (!parts.length) {
		parts.push(format_age_unit(days, __("day")));
	}

	frm.set_value("approximate_age", parts.join(" "));
}

function format_age_unit(value, unit) {
	const plural = value === 1 ? unit : `${unit}s`;
	return `${value} ${plural}`;
}

function create_owner_portal_user(frm) {
	frappe.db
		.get_value("Customer", frm.doc.primary_owner, ["customer_name", "email_id"])
		.then((result) => {
			const customer = result?.message || {};
			const dialog = new frappe.ui.Dialog({
				title: __("Create Owner Portal User"),
				fields: [
					{
						fieldname: "full_name",
						fieldtype: "Data",
						label: __("Owner Name"),
						default: customer.customer_name || frm.doc.primary_owner,
						reqd: 1,
					},
					{
						fieldname: "email",
						fieldtype: "Data",
						options: "Email",
						label: __("Owner Email"),
						default: customer.email_id || "",
						reqd: 1,
					},
					{
						fieldname: "send_welcome_email",
						fieldtype: "Check",
						label: __("Send Welcome Email"),
						default: 1,
					},
				],
				primary_action_label: __("Create / Link User"),
				primary_action(values) {
					frappe.call({
						method: "vetedge.services.portal_access.ensure_owner_portal_user_for_patient",
						args: {
							patient: frm.doc.name,
							email: values.email,
							full_name: values.full_name,
							send_welcome_email: values.send_welcome_email ? 1 : 0,
						},
						freeze: true,
						freeze_message: __("Preparing owner portal user..."),
						callback(response) {
							const message = response.message?.message || __("Owner portal user is ready.");
							frappe.msgprint({
								title: __("Owner Portal"),
								message,
								indicator: "green",
							});
							dialog.hide();
						},
					});
				},
			});
			dialog.show();
		});
}
