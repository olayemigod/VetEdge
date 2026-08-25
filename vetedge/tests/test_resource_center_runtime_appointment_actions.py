from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / "vetedge" / "hooks.py"
RESOURCE_BASE = ROOT / "vetedge" / "services" / "resource_center.py"
RESOURCE_V3 = ROOT / "vetedge" / "services" / "resource_center_v3.py"
RESOURCE_COMPONENT = (
    ROOT
    / "vetedge"
    / "public"
    / "js"
    / "vetedge_resource_center"
    / "VetEdgeResourceCenter.vue"
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_hooked_resource_center_provider_enriches_appointment_rows_with_smart_actions():
    hooks = read(HOOKS)
    base = read(RESOURCE_BASE)
    runtime = read(RESOURCE_V3)
    component = read(RESOURCE_COMPONENT)

    assert (
        '"vetedge.services.resource_center.get_resource_page": '
        '"vetedge.services.resource_center_v3.get_resource_page"'
    ) in hooks

    for contract in (
        "_with_appointment_action_states",
        "build_appointment_action_state",
        'frappe.get_cached_doc("Veterinary Appointment", row.name)',
        'row["_appointment_action_state"]',
    ):
        assert contract in base

    for contract in (
        "_with_runtime_appointment_actions",
        'if resource != "appointments"',
        'legacy._with_appointment_action_states({"key": "appointments"}, rows)',
        "_with_runtime_appointment_actions(resource, state)",
    ):
        assert contract in runtime

    for contract in (
        'v-for="action in appointmentActions(row)"',
        'row?._appointment_action_state?.actions || []',
        "vetedge.services.appointment_actions.perform_appointment_action",
        "expected_modified: row.modified",
    ):
        assert contract in component

    # Smart action state is included in the normal page response. The client
    # must not add a separate resolver request for every visible row.
    assert "get_appointment_action_state" not in component
