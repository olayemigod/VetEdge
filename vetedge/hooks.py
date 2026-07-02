app_name = "vetedge"
app_title = "VetEdge"
app_publisher = "ProcessEdge Solutions"
app_description = "VetEdge is a veterinary operations system built as a custom Frappe/ERPNext app."
app_email = "processedgeng@gmail.com"
app_license = "mit"
app_logo_url = "/assets/vetedge/images/vetedge-app-icon.png"
app_home = "/app/vetedge"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
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

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
app_include_css = [
	"/assets/vetedge/css/dashboard_shell.css",
	"/assets/vetedge/css/veterinary_unread_badge.css",
]
app_include_js = [
	"/assets/vetedge/js/dashboard_shell.js",
	"/assets/vetedge/js/invoice_summary_dialog.js",
	"/assets/vetedge/js/billing_modal.js",
	"/assets/vetedge/js/report_pdf_patch.js",
	"/assets/vetedge/js/report_visibility.js",
	"/assets/vetedge/js/veterinary_unread_badge.js",
]

# include js, css files in header of web template
# web_include_css = "/assets/vetedge/css/vetedge.css"
# web_include_js = "/assets/vetedge/js/vetedge.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "vetedge/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "vetedge/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }
get_website_user_home_page = "vetedge.services.portal_access.get_vetedge_website_user_home_page"

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "vetedge.utils.jinja_methods",
# 	"filters": "vetedge.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "vetedge.install.before_install"
after_install = "vetedge.install.after_install"
after_migrate = "vetedge.install.after_migrate"
boot_session = ["vetedge.coreedge_adapter.filter_bootinfo_for_coreedge_platform"]

# Uninstallation
# ------------

# before_uninstall = "vetedge.uninstall.before_uninstall"
# after_uninstall = "vetedge.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "vetedge.utils.before_app_install"
# after_app_install = "vetedge.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "vetedge.utils.before_app_uninstall"
# after_app_uninstall = "vetedge.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "vetedge.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

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

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Sales Invoice": {
		"before_validate": "vetedge.services.billing_core.normalize_vetedge_sales_invoice_dates",
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

# Scheduled Tasks
# ---------------

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

# Testing
# -------

before_tests = "vetedge.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "vetedge.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "vetedge.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "vetedge.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
before_request = ["vetedge.services.portal_access.block_owner_portal_desk_access"]
# after_request = ["vetedge.utils.after_request"]

# Job Events
# ----------
# before_job = ["vetedge.utils.before_job"]
# after_job = ["vetedge.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"vetedge.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
