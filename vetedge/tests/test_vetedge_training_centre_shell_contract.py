from pathlib import Path
import unittest


COMPONENT = (
    Path(__file__).resolve().parents[1]
    / "public"
    / "js"
    / "vetedge_training_centre"
    / "VetEdgeTrainingCentre.vue"
)


class TestVetEdgeTrainingCentreShellContract(unittest.TestCase):
    def test_uses_shared_edgesuite_shell(self):
        text = COMPONENT.read_text(encoding="utf-8")

        self.assertIn("<EdgeAppShell", text)
        self.assertIn("<EdgePageLayout>", text)
        self.assertIn('activeRoute="/app/veterinary-training-centre"', text)

    def test_does_not_hide_shared_sidebar(self):
        text = COMPONENT.read_text(encoding="utf-8")

        self.assertNotIn(
            ".vetedge-training-centre-root .edge-sidebar",
            text,
        )
        self.assertNotIn(
            ".vetedge-training-centre-root .edge-shell-sidebar",
            text,
        )
        self.assertNotIn(
            "display: none !important",
            text,
        )

    def test_does_not_override_shared_shell_dimensions(self):
        text = COMPONENT.read_text(encoding="utf-8")

        for selector in (
            ".vetedge-training-centre-root .edge-shell-body",
            ".vetedge-training-centre-root .edge-shell-main",
            ".vetedge-training-centre-root .edge-page-layout",
            ".vetedge-training-centre-root .edge-page-layout-body",
        ):
            self.assertNotIn(selector, text)

    def test_page_specific_training_styles_remain(self):
        text = COMPONENT.read_text(encoding="utf-8")

        for selector in (
            ".vtc-toolbar",
            ".vtc-role-filter",
            ".vtc-grid",
            ".vtc-card",
            ".vtc-reader",
            ".vtc-markdown",
        ):
            self.assertIn(selector, text)

    def test_role_group_filter_is_available(self):
        text = COMPONENT.read_text(encoding="utf-8")

        self.assertIn('v-model="roleFilter"', text)
        self.assertIn("availableRoleGroups", text)
        self.assertIn("module.role_group !== this.roleFilter", text)


if __name__ == "__main__":
    unittest.main()
