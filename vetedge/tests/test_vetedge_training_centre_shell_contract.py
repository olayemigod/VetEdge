from __future__ import annotations

from pathlib import Path
import unittest


TRAINING_COMPONENT = (
    Path(__file__).resolve().parents[1]
    / "public"
    / "js"
    / "vetedge_training_centre"
    / "VetEdgeTrainingCentre.vue"
)


def source() -> str:
    return TRAINING_COMPONENT.read_text(encoding="utf-8")


class TestVetEdgeTrainingCentreShellContract(unittest.TestCase):
    def test_training_centre_uses_shared_edgesuite_shell(self):
        text = source()

        self.assertIn("<EdgeAppShell", text)
        self.assertIn("<EdgePageLayout>", text)
        self.assertIn('activeRoute="/app/veterinary-training-centre"', text)

    def test_training_centre_does_not_override_shared_shell_layout(self):
        text = source()

        for selector in (
            ".vetedge-training-centre-root .edge-sidebar",
            ".vetedge-training-centre-root .edge-shell-sidebar",
            ".vetedge-training-centre-root .edge-shell-body",
            ".vetedge-training-centre-root .edge-shell-main",
            ".vetedge-training-centre-root .edge-page-layout",
            ".vetedge-training-centre-root .edge-page-layout-body",
        ):
            self.assertNotIn(selector, text)


if __name__ == "__main__":
    unittest.main()
