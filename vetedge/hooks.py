app_name = "vetedge"
app_title = "VetEdge"
app_publisher = "ProcessEdge Solutions"
app_description = "VetEdge is a veterinary operations system built as a custom Frappe/ERPNext app."
app_email = "processedgeng@gmail.com"
app_license = "mit"
app_logo_url = "/assets/vetedge/images/vetedge-app-icon.png"
app_home = "/app/vetedge-home"

# The standalone EdgeSuite UI app must be installed before VetEdge so shared
# product pages never depend on CoreEdge for their browser runtime.
required_apps = ["edgesuite_ui"]

add_to_apps_screen = [
	{
		"name": app_name,
		"logo": app_logo_url,
		"title": app_title,
		"route": app_home,
	}
]

portal_menu_items = [
	{"title": "Owner Portal", "route": "/vetedge_portal", "role": "VetEdge Portal User"},
	{"title": "Book Veterinary Appointment", "route": "/vetedge_guest_booking"},
]

app_include_css = [
	"/assets/vetedge/css/dashboard_shell.css",
	"/assets/vetedge/css/veterinary_unread_badge.css",
	"/assets/vetedge/css/vetedge_professional_ui.css?v=20260719-1",
]
app_include_js = [
	"/assets/vetedge/js/edgesuite_product_menu.js?v=20260718-3",
	"/assets/vetedge/js/vetedge_professional_ui.js?v=20260719-1",
	"/assets/vetedge/js/vetedge_ui_bridge.js?v=20260720-2",
	"/assets/vetedge/js/edgesuite_date_ranges.js",
	"/assets/vetedge/js/dashboard_shell.js",
	"/assets/vetedge/js/invoice_summary_dialog.js",
	"/assets/vetedge/js/billing_modal.js",
	"/assets/vetedge/js/report_pdf_patch.js",
	"/assets/vetedge/js/report_visibility.js",
	"/assets/vetedge/js/veterinary_unread_badge.js",
]

get_website_user_home_page = "vetedge.services.portal_access.get_vetedge_website_user_home_page"

after_install = "vetedge.install.after_install"
after_migrate = "vetedge.install.after_migrate"
boot_session = [
	"vetedge.coreedge_adapter.filter_bootinfo_for_coreedge_platform",
	"vetedge.ui_identity.extend_bootinfo",
]

override_whitelisted_methods = {
	"vetedge.services.medical_history.get_patient_medical_history_view": (
		"vetedge.services.medical_history_context.get_patient_medical_history_view"
	),
}

permission_query_conditions = {
	"Veterinary Patient": "vetedge.services.permissions.get_veterinary_patient_query",
	"Veterinary Appointment": "vetedge.services.permissions.get_veterinary_appointment_query",
	"Veterinary Missed Appointment": "vetedge.services.permissions.get_veterinary_missed_appointment_query",
	"Veterinary Consultation": "vetedge.services.permissions.get_veterinary_consultation_query",
	"Veterinary Vital Signs": "vetedge.services.permissions.get_veterinary_vital_signs_query",
	"Veterinary Lab Order": "vetedge.services.permissions.get_veterinary_lab_order_query",
	"Veterinary Vaccination Record": "vetedge.services.permissions.get_veterinary_vaccination_record_query",
	"Pet Grooming Appointment": "vetedge.services.permissions.get_pet_grooming_appointment_query",
	"Pet Grooming Session": "vetedge.services.permissions.get_pet_grooming_session_query",
	"Veterinary Guest Booking Request": "vetedge.services.permissions.get_veterinary_guest_booking_request_query",
	"Sales Invoice": "vetedge.services.permissions.get_sales_invoice_query",
	"Veterinary Notification Log": "vetedge.services.permissions.get_notification_admin_only_query",
	"Veterinary Notification Preference": "vetedge.services.permissions.get_notification_admin_only_query",
	"Veterinary Notification Item": "vetedge.services.permissions.get_veterinary_notification_item_query",
}

has_permission = {
	"Veterinary Patient": "vetedge.services.permissions.has_veterinary_patient_permission",
	"Sales Invoice": "vetedge.services.permissions.has_sales_invoice_permission",
	"Veterinary Vaccination Record": "vetedge.services.permissions.has_veterinary_vaccination_record_permission",
	"Veterinary Missed Appointment": "vetedge.services.permissions.has_veterinary_missed_appointment_permission",
	"Pet Grooming Appointment": "vetedge.services.permissions.has_pet_grooming_appointment_permission",
	"Pet Grooming Session": "vetedge.services.permissions.has_pet_grooming_session_permission",
	"Veterinary Notification Log": "vetedge.services.permissions.has_notification_admin_permission",
	"Veterinary Notification Preference": "vetedge.services.permissions.has_notification_admin_permission",
	"Veterinary Notification Item": "vetedge.services.permissions.has_veterinary_notification_item_permission",
}

doc_events = {
	"Branch": {
		"on_update": "vetedge.services.company_context_compat.sync_branch_company_context",
	},
	"Sales Invoice": {
		"before_validate": [
			"vetedge.services.billing_core.normalize_vetedge_sales_invoice_dates",
			"vetedge.services.appointment_quick_create_safety.align_registration_invoice_company_currency",
		],
		"before_save": "vetedge.services.branch_integrity.enforce_vetedge_invoice_branch",
		"on_update": [
			"vetedge.services.registration_billing.update_registration_status_from_invoice",
			"vetedge.services.billing.update_consultation_payment_status_from_invoice",
			"vetedge.services.vaccination.update_vaccination_status_from_invoice",
			"vetedge.services.grooming.update_grooming_status_from_invoice",
			"vetedge.services.billing_core.update_billing_sessions_from_invoice",
		],
		"on_update_after_submit": [
			"vetedge.services.registration_billing.update_registration_status_from_invoice",
			"vetedge.services.billing.update_consultation_payment_status_from_invoice",
			"vetedge.services.vaccination.update_vaccination_status_from_invoice",
			"vetedge.services.grooming.update_grooming_status_from_invoice",
			"vetedge.services.billing_core.update_billing_sessions_from_invoice",
		],
		"on_submit": [
			"vetedge.services.registration_billing.update_registration_status_from_invoice",
			"vetedge.services.billing.update_consultation_payment_status_from_invoice",
			"vetedge.services.vaccination.update_vaccination_status_from_invoice",
			"vetedge.services.grooming.update_grooming_status_from_invoice",
			"vetedge.services.billing_core.update_billing_sessions_from_invoice",
		],
		"on_cancel": [
			"vetedge.services.registration_billing.update_registration_status_from_invoice",
			"vetedge.services.billing.update_consultation_payment_status_from_invoice",
			"vetedge.services.vaccination.update_vaccination_status_from_invoice",
			"vetedge.services.grooming.update_grooming_status_from_invoice",
			"vetedge.services.billing_core.update_billing_sessions_from_invoice",
		],
	},
	"Payment Entry": {
		"on_submit": [
			"vetedge.services.registration_billing.update_registration_status_from_payment_entry",
			"vetedge.services.billing.update_consultation_payment_status_from_payment_entry",
			"vetedge.services.vaccination.update_vaccination_status_from_payment_entry",
			"vetedge.services.grooming.update_grooming_status_from_payment_entry",
			"vetedge.services.billing_core.update_billing_sessions_from_payment_entry",
		],
		"on_cancel": [
			"vetedge.services.registration_billing.update_registration_status_from_payment_entry",
			"vetedge.services.billing.update_consultation_payment_status_from_payment_entry",
			"vetedge.services.vaccination.update_vaccination_status_from_payment_entry",
			"vetedge.services.grooming.update_grooming_status_from_payment_entry",
			"vetedge.services.billing_core.update_billing_sessions_from_payment_entry",
		],
	},
	"Stock Entry": {
		"before_save": "vetedge.services.branch_integrity.enforce_vetedge_stock_entry_branch",
		"on_cancel": "vetedge.services.dispensary.sync_consultation_from_stock_entry",
	},
	"Veterinary Consultation": {
		"before_save": [
			"vetedge.services.branch_integrity.enforce_branch_integrity",
			"vetedge.services.practitioner_integrity.enforce_practitioner_integrity",
		],
	},
	"Veterinary Lab Order": {
		"before_save": [
			"vetedge.services.branch_integrity.enforce_branch_integrity",
			"vetedge.services.practitioner_integrity.enforce_practitioner_integrity",
		],
	},
	"Veterinary Vaccination Record": {
		"before_save": [
			"vetedge.services.branch_integrity.enforce_branch_integrity",
			"vetedge.services.practitioner_integrity.enforce_practitioner_integrity",
		],
	},
	"Veterinary Appointment": {
		"before_save": [
			"vetedge.services.branch_integrity.enforce_branch_integrity",
			"vetedge.services.practitioner_integrity.enforce_practitioner_integrity",
		],
	},
	"Pet Grooming Appointment": {
		"before_save": [
			"vetedge.services.branch_integrity.enforce_branch_integrity",
			"vetedge.services.practitioner_integrity.enforce_practitioner_integrity",
		],
	},
	"Pet Grooming Session": {
		"before_save": [
			"vetedge.services.branch_integrity.enforce_branch_integrity",
			"vetedge.services.practitioner_integrity.enforce_practitioner_integrity",
		],
	},
	"Pet Boarding Booking": {
		"before_save": "vetedge.services.branch_integrity.enforce_branch_integrity",
	},
	"Pet Boarding Stay": {
		"before_save": "vetedge.services.branch_integrity.enforce_branch_integrity",
	},
	"Pet Boarding Care Record": {
		"before_save": "vetedge.services.branch_integrity.enforce_branch_integrity",
	},
	"Kennel": {
		"before_save": "vetedge.services.branch_integrity.enforce_branch_integrity",
	},
}

scheduler_events = {
	"cron": {
		"*/5 * * * *": [
			"vetedge.services.appointment_notifications.run_appointment_notification_checks",
		],
	},
	"hourly": [
		"vetedge.services.notifications.send_due_appointment_reminders",
		"vetedge.services.appointment_flow.sync_missed_appointments",
	],
	"daily": [
		"vetedge.services.notifications.send_due_vaccination_notifications",
		"vetedge.services.notifications.send_payment_pending_reminders",
	],
}

before_tests = "vetedge.install.before_tests"
before_request = ["vetedge.services.portal_access.block_owner_portal_desk_access"]
