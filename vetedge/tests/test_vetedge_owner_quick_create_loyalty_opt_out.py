from pathlib import Path
from unittest import skipIf
from unittest.mock import patch

try:
	import frappe
	from frappe.tests.utils import FrappeTestCase
except ImportError:  # Fast source-contract validation runs without Frappe installed.
	frappe = None
	FrappeTestCase = object

ROOT = Path(__file__).resolve().parents[2]
SAFETY = ROOT / "vetedge" / "services" / "appointment_quick_create_safety.py"
HOOKS = ROOT / "vetedge" / "hooks.py"
COMPONENT = (
	ROOT
	/ "vetedge"
	/ "public"
	/ "js"
	/ "vetedge_resource_center"
	/ "VetEdgeAppointmentFlowV2.vue"
)


def read(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def test_appointment_owner_quick_create_keeps_loyalty_out_of_scope():
	safety = read(SAFETY)
	hooks = read(HOOKS)
	component = read(COMPONENT)

	owner_context = safety.split("def get_owner_quick_create_context", 1)[1].split(
		"def resolve_owner_loyalty_program", 1
	)[0]
	resolver = safety.split("def resolve_owner_loyalty_program", 1)[1].split(
		"def disable_customer_loyalty_auto_enrollment_for_quick_create", 1
	)[0]

	assert '"loyalty_programs": []' in owner_context
	assert '"requires_loyalty_program": False' in owner_context
	assert '"default_loyalty_program": ""' in owner_context
	assert "get_applicable_loyalty_programs(" not in owner_context
	assert "vetedge_skip_customer_loyalty_auto_enrollment" in resolver
	assert 'return ""' in resolver

	assert "disable_customer_loyalty_auto_enrollment_for_quick_create" in hooks
	assert "restore_customer_loyalty_auto_enrollment_after_quick_create" in hooks
	assert 'doc.__dict__["set_loyalty_program"] = lambda: None' in safety
	assert "doc.loyalty_program = None" in safety

	assert "owner_loyalty_programs" not in component
	assert "Loyalty Program" not in component


@skipIf(frappe is None, "Frappe runtime is required")
class TestAppointmentOwnerLoyaltyOptOut(FrappeTestCase):
	def test_customer_insert_skips_erpnext_loyalty_auto_enrollment(self):
		from vetedge.services.appointment_quick_create_safety import resolve_owner_loyalty_program
		from vetedge.services.guest_booking import get_default_customer_group, get_default_territory

		customer_group = get_default_customer_group()
		territory = get_default_territory()
		if not customer_group or not territory:
			self.skipTest("A Customer Group and Territory are required")

		customer_name = f"VetEdge Loyalty Opt Out {frappe.generate_hash(length=8)}"
		resolve_owner_loyalty_program({}, None)
		try:
			with patch(
				"erpnext.selling.doctype.customer.customer.Customer.set_loyalty_program",
				side_effect=AssertionError("ERPNext loyalty auto-enrollment must not run"),
			):
				customer = frappe.get_doc(
					{
						"doctype": "Customer",
						"customer_name": customer_name,
						"customer_type": "Individual",
						"customer_group": customer_group,
						"territory": territory,
					}
				)
				customer.insert(ignore_permissions=True)
		finally:
			frappe.flags.vetedge_skip_customer_loyalty_auto_enrollment = False

		self.assertFalse(customer.loyalty_program)
		self.assertFalse(customer.flags.get("vetedge_loyalty_auto_enrollment_suppressed"))
		self.assertNotIn("set_loyalty_program", customer.__dict__)
