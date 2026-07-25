from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from vetedge.services.clinical_workspace_phase5 import (
	_sort_treatment_order_rows,
	enforce_pending_dispensary_completion_invariant,
)


class TestVetEdgeClinicalWorkspacePhase5(FrappeTestCase):
	def test_completed_pending_dispensary_state_is_rejected(self):
		doc = frappe._dict(
			doctype="Veterinary Consultation",
			status="Completed",
			dispensary_status="Pending Dispensary",
		)
		with self.assertRaises(frappe.ValidationError):
			enforce_pending_dispensary_completion_invariant(doc)

	def test_non_completed_or_confirmed_dispensary_states_are_allowed(self):
		for status, dispensary_status in (
			("Pending Dispensary", "Pending Dispensary"),
			("Ready for Treatment", "Dispensary Confirmed"),
			("Completed", "Dispensary Confirmed"),
			("Completed", "Not Required"),
		):
			doc = frappe._dict(
				doctype="Veterinary Consultation",
				status=status,
				dispensary_status=dispensary_status,
			)
			enforce_pending_dispensary_completion_invariant(doc)

	def test_treatment_rows_are_newest_first_with_default_fee_last(self):
		rows = [
			frappe._dict(
				name="old-manual",
				idx=2,
				creation="2026-07-20 10:00:00",
				source_type="Treatment",
				source_detail_name=None,
			),
			frappe._dict(
				name="default-fee",
				idx=1,
				creation="2026-07-25 12:00:00",
				source_type="Consultation",
				source_detail_name="Default Consultation Fee",
			),
			frappe._dict(
				name="new-manual",
				idx=3,
				creation="2026-07-25 11:00:00",
				source_type="Treatment",
				source_detail_name=None,
			),
		]

		ordered = _sort_treatment_order_rows(rows)
		self.assertEqual([row.name for row in ordered], ["new-manual", "old-manual", "default-fee"])
