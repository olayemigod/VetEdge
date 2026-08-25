from __future__ import annotations

import ast
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
RELEASE_SAFETY = PACKAGE_ROOT / "services" / "boarding_billing_release_safety.py"
CHECKOUT_ALIGNMENT = PACKAGE_ROOT / "services" / "boarding_checkout_alignment.py"
CHECKOUT_ENDPOINT = PACKAGE_ROOT / "services" / "boarding_checkout_release_safety.py"
BILLING_ALIGNMENT = PACKAGE_ROOT / "services" / "billing_context_alignment.py"
BOOKING_CONTROLLER = PACKAGE_ROOT / "veterinary" / "doctype" / "pet_boarding_booking" / "pet_boarding_booking.py"
BOOKING_FORM = PACKAGE_ROOT / "veterinary" / "doctype" / "pet_boarding_booking" / "pet_boarding_booking.js"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestBoardingBillingReleaseSafetyContract(unittest.TestCase):
    def test_python_release_safety_files_parse(self):
        for path in (
            RELEASE_SAFETY,
            CHECKOUT_ALIGNMENT,
            CHECKOUT_ENDPOINT,
            BILLING_ALIGNMENT,
            BOOKING_CONTROLLER,
        ):
            ast.parse(source(path), filename=str(path))

    def test_reconciliation_is_cumulative_and_delta_based(self):
        text = source(RELEASE_SAFETY)

        self.assertIn("delta_amount = current_amount - submitted_amount", text)
        self.assertIn("delta_days = current_days - submitted_days", text)
        self.assertIn("unbilled_amount = current_amount - active_amount", text)
        self.assertIn("unbilled_days = current_days - active_days", text)
        self.assertIn("include_related=False", text)
        self.assertIn("get_billing_group_invoice_history", text)

    def test_adjustment_invoice_uses_delta_not_full_stay_charge(self):
        text = source(RELEASE_SAFETY)

        self.assertIn("build_boarding_adjustment_invoice_item", text)
        self.assertIn("delta_days,", text)
        self.assertIn("delta_amount,", text)
        self.assertNotIn("build_boarding_invoice_item(booking_doc", text)

    def test_existing_draft_is_updated_and_submitted_invoice_is_not_mutated(self):
        text = source(RELEASE_SAFETY)

        self.assertIn("update_draft_boarding_invoice", text)
        self.assertIn("if drafts:", text)
        self.assertNotIn("submitted[0].save", text)
        self.assertNotIn("submitted[0].set", text)
        self.assertNotIn("invoice.cancel()", text)

    def test_negative_delta_requires_financial_review(self):
        text = source(RELEASE_SAFETY)

        self.assertIn("has_negative_submitted_delta", text)
        self.assertIn("credit/refund treatment", text)
        self.assertIn("submitted Sales Invoices will not be reduced automatically", text)

    def test_checkout_no_longer_resyncs_boarding_into_billing_core(self):
        text = source(CHECKOUT_ALIGNMENT)

        self.assertIn("validate_boarding_checkout_release_safety", text)
        self.assertNotIn("sync_source_to_billing_session", text)
        self.assertNotIn("get_source_payment_gate_status", text)

    def test_checkout_validates_before_operational_completion(self):
        text = source(CHECKOUT_ENDPOINT)
        validation = text.index("validate_boarding_checkout_release_safety(doc)")
        stay_completion = text.index('stay_doc.status = "Completed"')
        booking_completion = text.index('doc.status = "Checked Out"')

        self.assertLess(validation, stay_completion)
        self.assertLess(validation, booking_completion)

    def test_booking_controller_enforces_checkout_invariant_on_save(self):
        text = source(BOOKING_CONTROLLER)

        self.assertIn("validate_boarding_checkout_release_safety", text)
        self.assertIn('if self.status == "Checked Out":', text)

    def test_standard_form_uses_release_safe_checkout_endpoint(self):
        text = source(BOOKING_FORM)

        self.assertIn(
            '"vetedge.services.boarding_checkout_release_safety.check_out_boarding_booking"',
            text,
        )
        self.assertNotIn(
            'transitionBoardingBooking(frm, "vetedge.services.boarding.check_out_boarding_booking"',
            text,
        )

    def test_billing_modal_routes_boarding_to_release_safety(self):
        text = source(BILLING_ALIGNMENT)

        self.assertIn("BOARDING_DOCTYPE = \"Pet Boarding Booking\"", text)
        self.assertIn("get_boarding_billing_modal_state", text)
        self.assertIn("create_or_update_boarding_delta_invoice", text)
        self.assertIn("submit_boarding_modal_invoice", text)
        self.assertIn("record_boarding_modal_payment", text)


if __name__ == "__main__":
    unittest.main()
