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
			frm.add_custom_button(__("Medical History"), () => {
				frappe.route_options = { patient: frm.doc.name };
				frappe.set_route("veterinary-medical-history");
			});
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
