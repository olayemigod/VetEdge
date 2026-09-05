from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EPISODE_COMPONENT = (
    ROOT
    / "vetedge"
    / "public"
    / "js"
    / "vetedge_hospitalisation_episode"
    / "VetEdgeHospitalisationEpisode.vue"
)
POLICY_V2 = ROOT / "vetedge" / "services" / "hospitalisation_episode_policy_v2.py"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def section(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


def test_hospitalisation_vaccination_ui_defers_billing_and_stock_to_linked_record():
    episode = read(EPISODE_COMPONENT)
    policy_v2 = read(POLICY_V2)
    vaccination_modal = section(
        episode,
        '<EdgeModal :open="vaccinationDialog.open"',
        '<EdgeModal :open="labDialog.open"',
    )
    vaccination_state = section(
        episode,
        "const blankVaccination =",
        "const blankLab =",
    )
    vaccination_save = section(
        episode,
        "async saveVaccination()",
        "openLab()",
    )

    assert 'label="Billable"' not in vaccination_modal
    assert 'label="Stock Affecting"' not in vaccination_modal
    assert "linked Vaccination Record" in vaccination_modal
    assert "clinical timeline reference only" in vaccination_modal
    assert "billable" not in vaccination_state
    assert "stock_affecting" not in vaccination_state
    assert "billable:" not in vaccination_save
    assert "stock_affecting:" not in vaccination_save
    assert 'type="datetime-local" label="Next Due Date/Time"' in vaccination_modal

    # The linked Vaccination Record remains the single billing/stock authority.
    assert '"billable": 0' in policy_v2
    assert '"stock_affecting": 0' in policy_v2
    assert "timeline reference only" in policy_v2
    assert "create_invoice=0" in policy_v2
    assert "post_stock=0" in policy_v2


def test_hospitalisation_lab_ui_surfaces_linked_order_authority_and_server_warning():
    episode = read(EPISODE_COMPONENT)
    lab_modal = section(
        episode,
        '<EdgeModal :open="labDialog.open"',
        '<EdgeModal :open="careDialog.open"',
    )
    lab_save = section(
        episode,
        "async saveLab()",
        "openCareLocation()",
    )

    assert "linked Lab Order" in lab_modal
    assert "clinical timeline reference only" in lab_modal
    assert 'label="Billable"' not in lab_modal
    assert 'label="Stock Affecting"' not in lab_modal
    assert "if (result?.warning) frappe.show_alert" in lab_save


def test_normal_hospitalisation_activity_keeps_meaningful_billing_and_stock_controls():
    episode = read(EPISODE_COMPONENT)
    activity_modal = section(
        episode,
        '<EdgeModal :open="activityDialog.open"',
        '<EdgeModal :open="vitalsDialog.open"',
    )

    assert 'label="Billable"' in activity_modal
    assert 'label="Stock Affecting"' in activity_modal
    assert 'label="Resolved Rate"' in activity_modal
