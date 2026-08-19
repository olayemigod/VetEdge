from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_training_centre_page_is_thin_edgesuite_mount_loader():
    page = (
        ROOT / "veterinary/page/veterinary_training_centre/veterinary_training_centre.js"
    ).read_text(encoding="utf-8")

    for expected in (
        "edgeui.bundle.js",
        "vetedge_training_centre.bundle.js",
        "mountVetEdgeTrainingCentre",
        "EdgeAppShell",
        "EdgePageLayout",
        "EdgePageHeader",
        "EdgeLoadingState",
        "EdgeErrorState",
        "EdgeEmptyState",
    ):
        assert expected in page

    assert "class VetEdgeTrainingCentre" not in page
    assert "add_styles()" not in page
    assert "render_markdown(" not in page
    assert len(page) < 6000


def test_training_centre_component_preserves_lazy_role_safe_content_loading():
    component = (
        ROOT / "public/js/vetedge_training_centre/VetEdgeTrainingCentre.vue"
    ).read_text(encoding="utf-8")
    backend = (ROOT / "services/training_centre.py").read_text(encoding="utf-8")

    for expected in (
        "<EdgeAppShell",
        "<EdgePageLayout",
        "<EdgePageHeader",
        "get_training_modules",
        "get_training_module_content",
        "await this.callFrappe(MODULES_API)",
        "await this.callFrappe(CONTENT_API",
        "video_embed_url",
        "loading=\"lazy\"",
        "MERMAID_ASSET = '/assets/vetedge/js/lib/mermaid.min.js'",
        "securityLevel: 'strict'",
        "data-training-module",
        "rel=\"noopener noreferrer\"",
    ):
        assert expected in component

    for expected in (
        "get_visible_training_modules()",
        "can_view_training_module(module)",
        "get_safe_youtube_embed_url",
        "youtube-nocookie.com",
        "resolve_markdown_path",
        "is_relative_to(training_root)",
    ):
        assert expected in backend

    assert "get_training_module_content(module_id" in backend
    assert "frappe.db.set_value" not in component
    assert ".save()" not in component


def test_training_centre_bundle_uses_shared_workspace_safety():
    bundle = (ROOT / "public/js/vetedge_training_centre.bundle.js").read_text(encoding="utf-8")
    assert "applyWorkspaceSafety" in bundle
    assert "mountVetEdgeTrainingCentre" in bundle
    assert "runtime.createEdgeApp" in bundle
