from pathlib import Path
import unittest


APP_ROOT = Path(__file__).resolve().parents[1]

COMPONENT = (
    APP_ROOT
    / "public"
    / "js"
    / "vetedge_training_centre"
    / "VetEdgeTrainingCentre.vue"
)

MERMAID_ASSET = APP_ROOT / "public" / "js" / "lib" / "mermaid.min.js"


def method_block(text: str, start: str, end: str) -> str:
    start_index = text.index(start)
    end_index = text.index(end, start_index)
    return text[start_index:end_index]


class TestVetEdgeTrainingCentreMermaidContract(unittest.TestCase):
    def test_mermaid_asset_is_packaged(self):
        self.assertTrue(MERMAID_ASSET.exists())

    def test_mermaid_render_waits_until_loading_panel_is_visible(self):
        text = COMPONENT.read_text(encoding="utf-8")
        block = method_block(
            text,
            "async openModule(moduleId, options = {}) {",
            "showList() {",
        )

        loading_done = block.index("this.moduleLoading = false;")
        next_tick = block.index("await this.$nextTick();", loading_done)
        render = block.index("await this.renderVisibleMermaid();", next_tick)

        self.assertLess(loading_done, next_tick)
        self.assertLess(next_tick, render)

    def test_mermaid_code_blocks_are_detected(self):
        text = COMPONENT.read_text(encoding="utf-8")

        self.assertIn("pre code.language-mermaid", text)
        self.assertIn("pre code[class*=\"mermaid\"]", text)

    def test_mermaid_runs_in_strict_mode_and_tracks_edgesuite_appearance(self):
        text = COMPONENT.read_text(encoding="utf-8")

        self.assertIn("securityLevel: 'strict'", text)
        self.assertIn("data-edge-appearance", text)
        self.assertIn("appearance === 'dark' ? 'dark' : 'default'", text)
        self.assertIn("theme", text)
        self.assertIn("this.mermaidTheme = theme;", text)


if __name__ == "__main__":
    unittest.main()
