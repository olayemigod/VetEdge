from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

if "frappe" not in sys.modules:
	sys.modules["frappe"] = SimpleNamespace(_=lambda value, *args, **kwargs: value)
	sys.modules["frappe.modules"] = SimpleNamespace()
	sys.modules["frappe.modules.import_file"] = SimpleNamespace(import_file_by_path=lambda *args, **kwargs: None)

MODULE_PATH = Path(__file__).resolve().parents[1] / "install" / "dashboard.py"
SPEC = importlib.util.spec_from_file_location("vetedge.install.dashboard_test_module", MODULE_PATH)
dashboard = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(dashboard)


class TestDashboardInstall(TestCase):
	def test_ensure_vetedge_workspace_sidebar_inserts_when_missing_without_exporting_json(self):
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(
				exists=Mock(side_effect=lambda doctype, name: doctype == "DocType" and name == "Workspace Sidebar")
			),
			flags=SimpleNamespace(in_import=False),
			cache=SimpleNamespace(delete_key=Mock()),
			rename_doc=Mock(),
			delete_doc=Mock(),
		)
		insert_states = []
		doc = SimpleNamespace(
			insert=Mock(side_effect=lambda **kwargs: insert_states.append(frappe_stub.flags.in_import))
		)
		frappe_stub.get_doc = Mock(return_value=doc)

		with patch.object(dashboard, "frappe", frappe_stub), patch.object(
			dashboard,
			"_load_standard_doc",
			return_value={"doctype": "Workspace Sidebar", "name": "VetEdge"},
		):
			dashboard.ensure_vetedge_workspace_sidebar()

		frappe_stub.get_doc.assert_called_once_with(
			{"doctype": "Workspace Sidebar", "name": "VetEdge", "title": "Veterinary", "items": []}
		)
		doc.insert.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(insert_states, [True])
		self.assertFalse(frappe_stub.flags.in_import)

	def test_ensure_vetedge_desktop_icon_inserts_when_missing(self):
		insert = Mock()
		db_set = Mock()
		doc = SimpleNamespace(insert=insert, db_set=db_set)
		exists = Mock(side_effect=lambda doctype, name: (doctype, name) == ("DocType", "Desktop Icon"))
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=exists, set_value=Mock()),
			get_doc=Mock(return_value=doc),
			cache=SimpleNamespace(delete_key=Mock()),
			rename_doc=Mock(),
			delete_doc=Mock(),
		)

		with patch.object(dashboard, "frappe", frappe_stub), patch.object(
			dashboard,
			"_load_standard_doc",
			return_value={"doctype": "Desktop Icon", "name": "VetEdge"},
		):
			dashboard.ensure_vetedge_desktop_icon()

		frappe_stub.get_doc.assert_called_once_with({"doctype": "Desktop Icon", "name": "VetEdge"})
		insert.assert_called_once_with(ignore_permissions=True)
		db_set.assert_called_once_with("label", "VetEdge")
		frappe_stub.db.set_value.assert_not_called()

	def test_ensure_vetedge_desktop_icon_updates_existing_icon(self):
		exists = Mock(
			side_effect=lambda doctype, name: (doctype, name)
			in {("DocType", "Desktop Icon"), ("Desktop Icon", "VetEdge")}
		)
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=exists, set_value=Mock()),
			get_doc=Mock(),
			cache=SimpleNamespace(delete_key=Mock()),
			rename_doc=Mock(),
			delete_doc=Mock(),
		)

		with patch.object(dashboard, "frappe", frappe_stub):
			dashboard.ensure_vetedge_desktop_icon()

		frappe_stub.get_doc.assert_not_called()
		frappe_stub.db.set_value.assert_called_once()
		update_values = frappe_stub.db.set_value.call_args.args[2]
		self.assertEqual(update_values["link_type"], "Workspace Sidebar")
		self.assertEqual(update_values["link"], "")
		self.assertEqual(update_values["link_to"], "VetEdge")

	def test_ensure_vetedge_workspace_sidebar_updates_only_when_changed_and_suppresses_export(self):
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(
				exists=Mock(
					side_effect=lambda doctype, name: (doctype, name)
					in {("DocType", "Workspace Sidebar"), ("Workspace Sidebar", "VetEdge")}
				)
			),
			flags=SimpleNamespace(in_import=False),
			cache=SimpleNamespace(delete_key=Mock()),
			rename_doc=Mock(),
			delete_doc=Mock(),
		)
		save_states = []
		sidebar = SimpleNamespace(
			as_dict=Mock(
				return_value={
					"doctype": "Workspace Sidebar",
					"name": "VetEdge",
					"title": "Old Title",
					"items": [],
				}
			),
			update=Mock(),
			save=Mock(side_effect=lambda **kwargs: save_states.append(frappe_stub.flags.in_import)),
			set=Mock(),
		)
		frappe_stub.get_doc = Mock(return_value=sidebar)

		with patch.object(dashboard, "frappe", frappe_stub), patch.object(
			dashboard,
			"_load_standard_doc",
			return_value={
				"doctype": "Workspace Sidebar",
				"name": "VetEdge",
				"title": "Veterinary",
				"items": [{"label": "Setup", "keep_closed": 1}],
			},
		):
			dashboard.ensure_vetedge_workspace_sidebar()

		frappe_stub.get_doc.assert_called_once_with("Workspace Sidebar", "VetEdge")
		sidebar.update.assert_called_once()
		sidebar.save.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(save_states, [True])
		self.assertFalse(frappe_stub.flags.in_import)

	def test_ensure_vetedge_workspace_sidebar_is_noop_when_database_matches_source(self):
		items = [{"label": "Setup", "keep_closed": 1}]
		sidebar = SimpleNamespace(
			as_dict=Mock(
				return_value={
					"doctype": "Workspace Sidebar",
					"name": "VetEdge",
					"title": "Veterinary",
					"items": items,
				}
			),
			update=Mock(),
			save=Mock(),
			set=Mock(),
		)
		exists = Mock(
			side_effect=lambda doctype, name: (doctype, name)
			in {("DocType", "Workspace Sidebar"), ("Workspace Sidebar", "VetEdge")}
		)
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=exists),
			flags=SimpleNamespace(in_import=False),
			get_doc=Mock(return_value=sidebar),
			cache=SimpleNamespace(delete_key=Mock()),
			rename_doc=Mock(),
			delete_doc=Mock(),
		)

		with patch.object(dashboard, "frappe", frappe_stub), patch.object(
			dashboard,
			"_load_standard_doc",
			return_value={
				"doctype": "Workspace Sidebar",
				"name": "VetEdge",
				"title": "Veterinary",
				"items": items,
			},
		):
			dashboard.ensure_vetedge_workspace_sidebar()

		sidebar.set.assert_not_called()
		sidebar.update.assert_not_called()
		sidebar.save.assert_not_called()
		self.assertFalse(frappe_stub.flags.in_import)

	def test_financial_dashboard_import_does_not_force_sidebar_file_before_runtime_filtering(self):
		self.assertNotIn(("workspace_sidebar", "vetedge.json"), dashboard.FINANCIAL_DASHBOARD_FILES)

	def test_workspace_sidebar_prunes_coreedge_links_when_coreedge_missing(self):
		installed_apps = Mock(return_value=["frappe", "erpnext", "vetedge"])
		exists = Mock(
			side_effect=lambda doctype, name=None: (
				True if doctype == "DocType" and name in ("Workspace Sidebar", "Veterinary Patient") else False
			)
		)
		sidebar_items = [
			{"label": "Patients", "type": "Link", "link_type": "DocType", "link_to": "Veterinary Patient"},
			{"label": "Platform Settings", "type": "Link", "link_type": "DocType", "link_to": "CoreEdge Settings"},
			{
				"label": "Product Activation",
				"type": "Link",
				"link_type": "DocType",
				"link_to": "CoreEdge Product Activation",
			},
		]

		class MockSidebar:
			def __init__(self):
				self.items = sidebar_items[:]

			def get(self, key):
				return self.items if key == "items" else None

			def set(self, key, value):
				if key == "items":
					self.items = value

			def update(self, payload):
				for key, value in payload.items():
					setattr(self, key, value)

			def save(self, **kwargs):
				pass

		sidebar = MockSidebar()
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=exists),
			flags=SimpleNamespace(in_import=False),
			get_installed_apps=installed_apps,
			get_doc=Mock(return_value=sidebar),
			cache=SimpleNamespace(delete_key=Mock()),
			rename_doc=Mock(),
			delete_doc=Mock(),
		)

		with patch.object(dashboard, "frappe", frappe_stub), patch.object(
			dashboard,
			"_load_standard_doc",
			return_value={
				"doctype": "Workspace Sidebar",
				"name": "VetEdge",
				"items": sidebar_items[:],
			},
		):
			dashboard.ensure_vetedge_workspace_sidebar()

		self.assertEqual(len(sidebar.items), 1)
		self.assertEqual(sidebar.items[0]["link_to"], "Veterinary Patient")

	def test_workspace_sidebar_preserves_coreedge_links_when_coreedge_available(self):
		installed_apps = Mock(return_value=["frappe", "erpnext", "vetedge", "coreedge"])
		exists = Mock(return_value=True)
		sidebar_items = [
			{"label": "Patients", "type": "Link", "link_type": "DocType", "link_to": "Veterinary Patient"},
			{"label": "Platform Settings", "type": "Link", "link_type": "DocType", "link_to": "CoreEdge Settings"},
		]

		class MockSidebar:
			def __init__(self):
				self.items = sidebar_items[:]

			def get(self, key):
				return self.items if key == "items" else None

			def set(self, key, value):
				if key == "items":
					self.items = value

			def update(self, payload):
				for key, value in payload.items():
					setattr(self, key, value)

			def save(self, **kwargs):
				pass

		sidebar = MockSidebar()
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=exists),
			flags=SimpleNamespace(in_import=False),
			get_installed_apps=installed_apps,
			get_doc=Mock(return_value=sidebar),
			cache=SimpleNamespace(delete_key=Mock()),
			rename_doc=Mock(),
			delete_doc=Mock(),
		)

		with patch.object(dashboard, "frappe", frappe_stub), patch.object(
			dashboard,
			"_load_standard_doc",
			return_value={
				"doctype": "Workspace Sidebar",
				"name": "VetEdge",
				"items": sidebar_items[:],
			},
		):
			dashboard.ensure_vetedge_workspace_sidebar()

		self.assertEqual(len(sidebar.items), 2)

	def test_cleanup_legacy_workspace_sidebars_removes_stale_dashboard_sidebars(self):
		deleted = []
		exists = Mock(
			side_effect=lambda doctype, name=None: (
				doctype == "DocType" and name == "Workspace Sidebar"
			)
			or (
				doctype == "Workspace Sidebar"
				and name in ("Veterinary Hospitalisation Dashboard", "Veterinary Financial Dashboard")
			)
		)
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=exists),
			delete_doc=lambda doctype, name, force=False: deleted.append((doctype, name, force)),
		)

		with patch.object(dashboard, "frappe", frappe_stub):
			dashboard.cleanup_legacy_workspace_sidebars()

		self.assertEqual(
			deleted,
			[
				("Workspace Sidebar", "Veterinary Hospitalisation Dashboard", True),
				("Workspace Sidebar", "Veterinary Financial Dashboard", True),
			],
		)
