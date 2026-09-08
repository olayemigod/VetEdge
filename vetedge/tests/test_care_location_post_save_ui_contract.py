from __future__ import annotations

from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
CARE_LOCATION_PAGE = APP_ROOT / "veterinary" / "page" / "vetedge_care_locations" / "vetedge_care_locations.js"


def test_care_location_save_closes_editor_and_refreshes_without_blank_loading_state():
    source = CARE_LOCATION_PAGE.read_text(encoding="utf-8")

    assert "async refresh({ silent = false } = {})" in source
    assert "if (!silent) {" in source
    assert "const wasNew = Boolean(this.editor.document?.is_new);" in source
    assert "this.editor.open = false;" in source
    assert "this.clearEditorRoute();" in source
    assert "if (wasNew) this.pageStart = 0;" in source
    assert "await this.refresh({ silent: true });" in source

    save_start = source.index("async saveDocument()")
    save_end = source.index("requestDelete()", save_start)
    save_block = source[save_start:save_end]
    assert "this.setEditorRoute(doc);" not in save_block
    assert "await this.refresh();" not in save_block


def test_care_location_delete_uses_non_blank_background_refresh():
    source = CARE_LOCATION_PAGE.read_text(encoding="utf-8")

    delete_start = source.index("async deleteDocument()")
    delete_end = source.index("renderFilters()", delete_start)
    delete_block = source[delete_start:delete_end]
    assert "this.editor.open = false;" in delete_block
    assert "this.clearEditorRoute();" in delete_block
    assert "await this.refresh({ silent: true });" in delete_block
    assert "await this.refresh();" not in delete_block
