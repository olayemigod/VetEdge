from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_legacy_kennel_pages_are_thin_router_first_compatibility_redirects():
    snapshot = (
        ROOT / "veterinary/page/kennel_availability/kennel_availability.js"
    ).read_text(encoding="utf-8")
    board = (
        ROOT / "veterinary/page/kennel_availability_board/kennel_availability_board.js"
    ).read_text(encoding="utf-8")

    for source in (snapshot, board):
        assert "/desk/vetedge-service-operations?resource=availability" in source
        assert "frappe?.router?.route" in source
        assert "window.history?.replaceState" in source
        assert "window.location.replace(target)" in source
        assert "frappe.call(" not in source
        assert "<table" not in source
        assert "class VetEdgeKennel" not in source
        assert len(source) < 1800


def test_legacy_appointment_queue_is_router_first_front_desk_alias():
    source = (
        ROOT / "veterinary/page/veterinary_appointment_queue/veterinary_appointment_queue.js"
    ).read_text(encoding="utf-8")

    assert "/desk/vetedge-front-desk-action-center?tab=queue" in source
    assert "frappe?.router?.route" in source
    assert "window.history?.replaceState" in source
    assert "window.location.replace(target)" in source
    assert "frappe.call(" not in source
    assert len(source) < 1800


def test_service_operations_is_canonical_kennel_availability_surface():
    component = (
        ROOT / "public/js/vetedge_service_operations/VetEdgeServiceOperations.vue"
    ).read_text(encoding="utf-8")

    for expected in (
        'requested = params.get("resource") || "availability"',
        'resource === \'availability\'',
        'availability: "vetedge.services.boarding.get_kennel_availability_board_view"',
        "<EdgeDataTable",
        "Kennel Availability",
    ):
        assert expected in component
