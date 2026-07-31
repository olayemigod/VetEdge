from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "vetedge"


class TestEdgeSuiteKeyboardCommandsContract(unittest.TestCase):
	def test_shared_keyboard_commands_are_loaded_first(self):
		hooks = (APP / "hooks.py").read_text()
		keyboard = hooks.index('"/assets/vetedge/js/edgesuite_keyboard_shortcuts.js"')
		product_menu = hooks.index('"/assets/vetedge/js/edgesuite_product_menu.js')
		self.assertLess(keyboard, product_menu)

	def test_commands_preserve_frappe_document_safety(self):
		asset = (APP / "public/js/edgesuite_keyboard_shortcuts.js").read_text()
		for expected in (
			'COMMAND_VERSION = "1.0.0"',
			"registerSaveHandler",
			"edgesuite:save-request",
			"edgesuite:command-palette-request",
			"form.doc.docstatus",
			"form.is_dirty()",
			"form.save()",
			"data-edgesuite-save",
			'key === "s"',
			'key === "k"',
		):
			self.assertIn(expected, asset)
		for forbidden in (
			"ignore_permissions",
			"frappe.db.set_value",
			"frappe.client.save",
			"form.doc.docstatus = 0",
		):
			self.assertNotIn(forbidden, asset)


if __name__ == "__main__":
	unittest.main()
