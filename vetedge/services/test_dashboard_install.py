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
	def test_ensure_vetedge_workspace_sidebar_inserts_when_missing(self):
		insert = Mock()
		db_set = Mock()
		doc = SimpleNamespace(insert=insert, db_set=db_set)
		exists = Mock(side_effect=lambda doctype, name: doctype == "DocType" and name == "Workspace Sidebar")
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=exists),
			get_doc=Mock(return_value=doc),
			rename_doc=Mock(),
			delete_doc=Mock(),
		)

		with patch.object(dashboard, "frappe", frappe_stub), patch.object(
			dashboard,
			"_load_standard_doc",
			return_value={"doctype": "Workspace Sidebar", "name": "VetEdge"},
		):
			dashboard.ensure_vetedge_workspace_sidebar()

		created_sidebar = frappe_stub.get_doc.call_args.args[0]
		self.assertEqual(created_sidebar["title"], "Veterinary")
		self.assertEqual(created_sidebar["items"][0]["label"], "Veterinary Home")
		insert.assert_called_once_with(ignore_permissions=True)
		db_set.assert_called_once_with("title", "Veterinary")

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
		db_set.assert_called_once_with("label", "Veterinary")
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


	def test_ensure_vetedge_workspace_sidebar_updates_existing_sidebar(self):
		sidebar = SimpleNamespace(update=Mock(), save=Mock(), db_set=Mock(), set=Mock())
		exists = Mock(side_effect=lambda doctype, name: (doctype, name) in {("DocType", "Workspace Sidebar"), ("Workspace Sidebar", "VetEdge")})
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=exists),
			get_doc=Mock(return_value=sidebar),
			cache=SimpleNamespace(delete_key=Mock()),
			rename_doc=Mock(),
			delete_doc=Mock(),
		)

		with patch.object(dashboard, "frappe", frappe_stub), patch.object(
			dashboard,
			"_load_standard_doc",
			return_value={"doctype": "Workspace Sidebar", "name": "VetEdge", "items": [{"label": "Setup", "keep_closed": 1}]},
		):
			dashboard.ensure_vetedge_workspace_sidebar()

		frappe_stub.get_doc.assert_called_once_with("Workspace Sidebar", "VetEdge")
		sidebar.update.assert_called_once()
		sidebar.save.assert_called_once_with(ignore_permissions=True)
		sidebar.db_set.assert_called_once_with("title", "Veterinary")

	def test_workspace_sidebar_prunes_coreedge_links_when_coreedge_missing(self):
		# Simulate CoreEdge missing (not installed and doctypes do not exist)
		installed_apps = Mock(return_value=["frappe", "erpnext", "vetedge"])

		exists = Mock(side_effect=lambda doctype, name=None: (
			True if doctype == "DocType" and name in ("Workspace Sidebar", "Veterinary Patient")
			else False
		))

		sidebar_items = [
			{"label": "Patients", "type": "Link", "link_type": "DocType", "link_to": "Veterinary Patient"},
			{"label": "Platform Settings", "type": "Link", "link_type": "DocType", "link_to": "CoreEdge Settings"},
			{"label": "Product Activation", "type": "Link", "link_type": "DocType", "link_to": "CoreEdge Product Activation"},
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
				pass
			def save(self, **kwargs):
				pass
			def insert(self, **kwargs):
				pass
			def db_set(self, key, value):
				pass

		sidebar = MockSidebar()

		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=exists),
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
				"items": sidebar_items[:]
			},
		):
			dashboard.ensure_vetedge_workspace_sidebar()

		# CoreEdge links must be pruned; the home link and patient link remain.
		self.assertEqual(len(sidebar.items), 2)
		self.assertEqual(
			[item.get("link_to") for item in sidebar.items if item.get("link_to")],
			["Veterinary Patient"],
		)

	def test_workspace_sidebar_preserves_coreedge_links_when_coreedge_available(self):
		# Simulate CoreEdge installed and DocTypes exist
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
				pass
			def save(self, **kwargs):
				pass
			def insert(self, **kwargs):
				pass
			def db_set(self, key, value):
				pass

		sidebar = MockSidebar()

		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=exists),
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
				"items": sidebar_items[:]
			},
		):
			dashboard.ensure_vetedge_workspace_sidebar()

		# CoreEdge links must NOT be pruned because CoreEdge is installed and doctype exists
		self.assertEqual(len(sidebar.items), 2)

	def test_v16_sidebar_prunes_missing_coreedge_targets(self):
		coreedge_item = SimpleNamespace(
			label="Platform Settings",
			link_type="DocType",
			link_to="CoreEdge Settings",
		)
		patient_item = SimpleNamespace(
			label="Patients",
			link_type="DocType",
			link_to="Veterinary Patient",
		)

		class MockSidebar:
			def __init__(self):
				self.items = [patient_item, coreedge_item]
				self.save = Mock()

			def remove(self, item):
				self.items.remove(item)

		sidebar = MockSidebar()
		exists = Mock(
			side_effect=lambda doctype, name=None: (
				True
				if (doctype, name) in {
					("DocType", "Sidebar"),
					("Sidebar", "Veterinary"),
					("DocType", "Veterinary Patient"),
				}
				else False
			)
		)
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=exists),
			get_installed_apps=Mock(return_value=["frappe", "erpnext", "vetedge"]),
			get_doc=Mock(return_value=sidebar),
			cache=SimpleNamespace(delete_key=Mock()),
		)

		with patch.object(dashboard, "frappe", frappe_stub), patch.object(
			dashboard, "_import_standard_files"
		):
			dashboard.ensure_vetedge_workspace_sidebar()

		self.assertEqual(sidebar.items, [patient_item])
		sidebar.save.assert_called_once_with(ignore_permissions=True)
		frappe_stub.cache.delete_key.assert_called_once_with("bootinfo")

	def test_v16_sidebar_keeps_available_coreedge_targets(self):
		coreedge_item = SimpleNamespace(
			label="Platform Settings",
			link_type="DocType",
			link_to="CoreEdge Settings",
		)
		sidebar = SimpleNamespace(items=[coreedge_item], save=Mock(), remove=Mock())
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=Mock(return_value=True)),
			get_installed_apps=Mock(return_value=["frappe", "erpnext", "vetedge", "coreedge"]),
			get_doc=Mock(return_value=sidebar),
			cache=SimpleNamespace(delete_key=Mock()),
		)

		with patch.object(dashboard, "frappe", frappe_stub), patch.object(
			dashboard, "_import_standard_files"
		):
			dashboard.ensure_vetedge_workspace_sidebar()

		sidebar.remove.assert_not_called()
		sidebar.save.assert_not_called()

	def test_cleanup_legacy_workspace_sidebars_removes_stale_dashboard_sidebars(self):
		deleted = []
		exists = Mock(
			side_effect=lambda doctype, name=None: (
				doctype == "DocType"
				and name == "Workspace Sidebar"
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
