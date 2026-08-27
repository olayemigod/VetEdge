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

    def test_successful_save_refreshes_then_closes_editor(self):
        text = source()
        block = method_block(text, "async saveDocument() {", "async deleteDocument() {")

        refresh_index = block.index("await this.refresh();")
        release_busy_index = block.index("this.editor.saving = false;", refresh_index)
        close_index = block.index("this.closeEditor();", release_busy_index)

        self.assertLess(refresh_index, release_busy_index)
        self.assertLess(release_busy_index, close_index)

    def test_all_five_resources_share_the_same_editor_lifecycle(self):
        text = source()
        self.assertEqual(text.count('{ key: "'), 5)
        for resource in (
            "notification-preferences",
            "notification-logs",
            "notification-items",
            "role-bundles",
            "license-profile",
        ):
            self.assertIn(f'key: "{resource}"', text)


if __name__ == "__main__":
    unittest.main()
