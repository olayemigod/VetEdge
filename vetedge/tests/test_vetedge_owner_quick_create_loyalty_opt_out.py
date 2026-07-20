from pathlib import Path

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
