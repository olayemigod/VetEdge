from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_service_operations_exposes_boarding_and_grooming_business_documents():
    service = read("vetedge/services/service_operations.py")
    component = read("vetedge/public/js/vetedge_service_operations/VetEdgeServiceOperations.vue")
    bundle = read("vetedge/public/js/vetedge_service_operations.bundle.js")

    assert '"boarding-bookings"' in service
    assert '"doctype": "Pet Boarding Booking"' in service
    assert '"editor_resource": "boarding"' in service
    assert '"grooming-appointments"' in service
    assert '"doctype": "Pet Grooming Appointment"' in service
    assert '"editor_resource": "grooming"' in service

    assert 'value: "boarding-bookings"' in component
    assert "GROOMING_APPOINTMENTS_TAB" in bundle
    assert "value: 'grooming-appointments'" in bundle
    assert "state.resource = GROOMING_APPOINTMENTS_TAB.value" in bundle
    assert "New Boarding Booking" in component
    assert "New Grooming Appointment" in bundle
    assert "/desk/vetedge-resource-center?resource=" in component


def test_grooming_appointment_deep_link_stays_in_service_operations_detail():
    bundle = read("vetedge/public/js/vetedge_service_operations.bundle.js")
    component = read("vetedge/public/js/vetedge_service_operations/VetEdgeServiceOperations.vue")
    page = read("vetedge/veterinary/page/vetedge_service_operations/vetedge_service_operations.js")

    assert "'grooming-appointments'" in page
    assert "requestedServiceResource() === GROOMING_APPOINTMENTS_TAB.value" in bundle
    assert 'requestedName: params.get("name") || ""' in component
    assert 'if (this.requestedName && this.resource !== "availability")' in component
    assert "await this.openDetail({ name });" in component


def test_boarding_actions_reuse_server_workflow_and_billing_truth():
    service = read("vetedge/services/service_operations.py")
    component = read("vetedge/public/js/vetedge_service_operations/VetEdgeServiceOperations.vue")
    billing_modal = read("vetedge/services/billing_modal.py")

    for handler in (
        "reserve_boarding_booking_doc",
        "check_in_boarding_booking_doc",
        "check_out_boarding_booking_doc",
        "cancel_boarding_booking_doc",
    ):
        assert handler in service

    assert '"billing", "label": _("Billing / Payment")' in service
    assert '"target_doctype": "Pet Boarding Booking"' in service
    assert '"Pet Boarding Booking": BillingSourceConfig(' in billing_modal
    assert 'boarding: "vetedge.services.service_operations.transition_boarding_booking"' in component
    assert 'if (action.key === "billing" || action.key === "billing-target")' in component


def test_service_order_delete_fails_closed_after_financial_or_delivery_commitment():
    service = read("vetedge/services/service_operations.py")

    assert "def _has_billing_core_evidence" in service
    assert '"Veterinary Billing Session Charge"' in service
    assert "def _has_financial_evidence" in service
    assert "def _can_delete_service_order" in service
    assert 'return doc.status == "Draft" and not doc.get("linked_stay")' in service
    assert 'if doc.status != "Scheduled":' in service
    assert 'frappe.db.exists("Pet Grooming Session", {"appointment": doc.name})' in service
    assert "_archive_and_detach_notifications" in service
    assert "has progressed into service delivery or has billing history" in service


def test_grooming_session_creation_is_explicit_and_does_not_hide_invoice_creation():
    service = read("vetedge/services/service_operations.py")
    component = read("vetedge/public/js/vetedge_service_operations/VetEdgeServiceOperations.vue")
    billing_modal = read("vetedge/services/billing_modal.py")

    assert "def create_or_open_grooming_session" in service
    assert "create_grooming_session_from_appointment(appointment, create_invoice=0)" in service
    assert '"create-grooming-session"' in service
    assert '"Pet Grooming Session": BillingSourceConfig(' in billing_modal
    assert 'createGroomingSession: "vetedge.services.service_operations.create_or_open_grooming_session"' in component
    assert 'return this.openBilling(action)' in component


def test_service_operations_busy_state_covers_server_actions():
    component = read("vetedge/public/js/vetedge_service_operations/VetEdgeServiceOperations.vue")

    assert ':busy="detail.loading || busy"' in component
    assert ':busy="busy"' in component
    assert "this.busy = true" in component
    assert "finally { this.busy = false; }" in component
