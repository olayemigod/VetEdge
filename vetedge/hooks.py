app_name = "vetedge"
app_title = "VetEdge"
app_publisher = "ProcessEdge Solutions"
app_description = "VetEdge is a veterinary operations system built as a custom Frappe/ERPNext app."
app_email = "processedgeng@gmail.com"
app_license = "mit"
app_logo_url = "/assets/vetedge/images/vetedge-app-icon.png"
app_home = "/desk/vetedge"

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
	"/assets/vetedge/css/vetedge_navigation_shell_compat.css?v=20260812-1",
]
app_include_js = [
	"/assets/vetedge/js/edgesuite_product_menu.js?v=20260810-2",
	"/assets/vetedge/js/vetedge_professional_ui.js?v=20260719-1",
	"/assets/vetedge/js/vetedge_ui_bridge.js?v=20260810-2",
	"/assets/vetedge/js/vetedge_navigation_recovery.js?v=20260812-2",
	"/assets/vetedge/js/edgesuite_date_ranges.js",
	"/assets/vetedge/js/dashboard_shell.js",
	"/assets/vetedge/js/invoice_summary_dialog.js",
	"/assets/vetedge/js/billing_modal.js",
	"/assets/vetedge/js/vetedge_shared_billing_edgesuite.js?v=20260815-1",
	"/assets/vetedge/js/vetedge_billing_modal_alignment.js?v=20260814-1",
	"/assets/vetedge/js/vetedge_billing_modal_layering.js?v=20260814-1",
	"/assets/vetedge/js/vetedge_resource_center_action_alignment.js?v=20260814-1",
	"/assets/vetedge/js/vetedge_resource_center_hardening.js?v=20260815-1",
	"/assets/vetedge/js/vetedge_lab_order_add_tests.js?v=20260815-1",
	"/assets/vetedge/js/vetedge_sidebar_qa_alignment.js?v=20260814-1",
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

override_whitelisted_methods = {
	"vetedge.services.reporting_logic_v4.get_dashboard_payload": "vetedge.services.reporting_logic_v5.get_dashboard_payload",
	"vetedge.services.reporting_logic_v5.get_dashboard_payload": "vetedge.services.dashboard_host_payload.get_dashboard_payload",
	"vetedge.services.front_desk_action_center.get_front_desk_link_options": "vetedge.services.front_desk_link_search.get_front_desk_link_options",
	"vetedge.services.master_workspace.get_master_link_options": "vetedge.services.master_link_search.get_master_link_options",
	"vetedge.services.appointment_edgeui.search_appointment_link": "vetedge.services.appointment_link_search.search_appointment_link",
	"vetedge.services.clinical_workspace.get_clinical_link_options": "vetedge.services.remaining_link_search.get_clinical_link_options",
	"vetedge.services.pricing_master_workspace.get_pricing_master_link_options": "vetedge.services.remaining_link_search.get_pricing_master_link_options",
	"vetedge.services.resource_center.get_resource_page": "vetedge.services.resource_center_v3.get_resource_page",
	"vetedge.services.resource_center.get_resource_editor": "vetedge.services.resource_editor_state.get_resource_editor",
	"vetedge.services.resource_center.save_resource_record": "vetedge.services.resource_editor_state.save_resource_record",
	"vetedge.services.billing_modal.get_billing_modal_state": "vetedge.services.billing_context_alignment.get_billing_modal_state",
	"vetedge.services.billing_modal.create_or_update_modal_invoice": "vetedge.services.billing_context_alignment.create_or_update_modal_invoice",
	"vetedge.services.billing_modal.submit_modal_invoice": "vetedge.services.billing_context_alignment.submit_modal_invoice",
	"vetedge.services.billing_modal.record_modal_invoice_payment": "vetedge.services.billing_context_alignment.record_modal_invoice_payment",
	"vetedge.services.clinical_record_editor.get_clinical_record_editor": "vetedge.services.clinical_record_state_v2.get_clinical_record_editor",
	"vetedge.services.clinical_record_editor.get_lab_result_editor": "vetedge.services.clinical_record_state_v2.get_lab_result_editor",
	"vetedge.services.clinical_record_editor.create_clinical_record": "vetedge.services.mutation_security.create_clinical_record",
	"vetedge.services.clinical_record_editor.save_clinical_record_editor": "vetedge.services.mutation_security.save_clinical_record_editor",
	"vetedge.services.clinical_record_editor.delete_clinical_record": "vetedge.services.mutation_security.delete_clinical_record",
	"vetedge.services.clinical_record_editor.save_lab_result_editor": "vetedge.services.mutation_security.save_lab_result_editor",
	"vetedge.services.clinical_record_editor.save_lab_test_rate": "vetedge.services.mutation_security.save_lab_test_rate",
	"vetedge.services.lab.transition_lab_order_status": "vetedge.services.mutation_security.transition_lab_order_status",
	"vetedge.services.registration_billing.create_manual_registration_invoice": "vetedge.services.mutation_security.create_manual_registration_invoice",
	"vetedge.services.grooming.transition_grooming_session_status": "vetedge.services.grooming_payment_workflow.transition_grooming_session_status",
	"vetedge.services.service_operations.get_service_operation_detail": "vetedge.services.service_operations_state.get_service_operation_detail",
	"vetedge.services.service_operations.transition_grooming_session": "vetedge.services.service_operations_state.transition_grooming_session",
}

# Existing document event, scheduler and request hooks continue below unchanged.
# This compact continuation marker is intentionally not executable configuration.
