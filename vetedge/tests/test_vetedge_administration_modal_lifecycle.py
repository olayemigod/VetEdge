from __future__ import annotations

from pathlib import Path
import unittest


ADMINISTRATION_JS = (
    Path(__file__).resolve().parents[1]
    / "veterinary"
    / "page"
    / "vetedge_administration"
    / "vetedge_administration.js"
)


def source() -> str:
    return ADMINISTRATION_JS.read_text(encoding="utf-8")


def method_block(text: str, start: str, end: str) -> str:
    start_index = text.index(start)
    end_index = text.index(end, start_index)
    return text[start_index:end_index]


class TestVetEdgeAdministrationModalLifecycle(unittest.TestCase):
    def test_editor_modal_is_conditionally_mounted_with_stable_key(self):
        text = source()
        block = method_block(text, "renderEditor() {", "renderDeleteConfirmation() {")

        self.assertIn("if (!this.editor.open) return null;", block)
        self.assertIn('key: "vetedge-administration-editor-modal"', block)
        self.assertIn("open: true", block)
        self.assertNotIn("open: this.editor.open", block)

    def test_delete_modal_is_conditionally_mounted_with_stable_key(self):
        text = source()
        block = method_block(text, "renderDeleteConfirmation() {", "\n\t\t\t\t},\n\t\t\t},\n\t\t\trender() {")

        self.assertIn("if (!this.confirmDeleteOpen) return null;", block)
        self.assertIn('key: "vetedge-administration-delete-modal"', block)
        self.assertIn("open: true", block)
        self.assertNotIn("open: this.confirmDeleteOpen", block)

    def test_successful_save_closes_editor_before_refreshing_list(self):
        text = source()
        block = method_block(text, "async saveDocument() {", "async deleteDocument() {")

        self.assertNotIn("this.updateRoute(doc);", block)
        release_busy_index = block.index("this.editor.saving = false;")
        close_index = block.index("this.editor.open = false;", release_busy_index)
        first_page_index = block.index("this.pageStart = 0;", close_index)
        route_index = block.index("this.updateRoute();", first_page_index)
        next_tick_index = block.index("await this.$nextTick();", route_index)
        refresh_index = block.index("await this.refresh();", next_tick_index)

        self.assertLess(release_busy_index, close_index)
        self.assertLess(close_index, first_page_index)
        self.assertLess(first_page_index, route_index)
        self.assertLess(route_index, next_tick_index)
        self.assertLess(next_tick_index, refresh_index)

    def test_all_five_resources_share_the_same_editor_lifecycle(self):
        text = source()
        resource_block = method_block(
            text,
            "const VETEDGE_ADMIN_RESOURCES = Object.freeze([",
            "const VETEDGE_ADMIN_STYLE_ID",
        )
        self.assertEqual(resource_block.count('{ key: "'), 5)
        for resource in (
            "notification-preferences",
            "notification-logs",
            "notification-items",
            "role-bundles",
            "license-profile",
        ):
            self.assertIn(f'key: "{resource}"', resource_block)


if __name__ == "__main__":
    unittest.main()
