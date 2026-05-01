from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

if "frappe" not in sys.modules:
	sys.modules["frappe"] = SimpleNamespace()
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
		doc = SimpleNamespace(insert=insert)
		exists = Mock(side_effect=lambda doctype, name: doctype == "DocType" and name == "Workspace Sidebar")
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=exists),
			get_doc=Mock(return_value=doc),
		)

		with patch.object(dashboard, "frappe", frappe_stub), patch.object(
			dashboard,
			"_load_standard_doc",
			return_value={"doctype": "Workspace Sidebar", "name": "VetEdge"},
		):
			dashboard.ensure_vetedge_workspace_sidebar()

		frappe_stub.get_doc.assert_called_once_with({"doctype": "Workspace Sidebar", "name": "VetEdge"})
		insert.assert_called_once_with(ignore_permissions=True)

	def test_ensure_vetedge_desktop_icon_inserts_when_missing(self):
		insert = Mock()
		doc = SimpleNamespace(insert=insert)
		exists = Mock(side_effect=lambda doctype, name: (doctype, name) == ("DocType", "Desktop Icon"))
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=exists, set_value=Mock()),
			get_doc=Mock(return_value=doc),
			cache=SimpleNamespace(delete_key=Mock()),
		)

		with patch.object(dashboard, "frappe", frappe_stub), patch.object(
			dashboard,
			"_load_standard_doc",
			return_value={"doctype": "Desktop Icon", "name": "VetEdge"},
		):
			dashboard.ensure_vetedge_desktop_icon()

		frappe_stub.get_doc.assert_called_once_with({"doctype": "Desktop Icon", "name": "VetEdge"})
		insert.assert_called_once_with(ignore_permissions=True)
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
		)

		with patch.object(dashboard, "frappe", frappe_stub):
			dashboard.ensure_vetedge_desktop_icon()

		frappe_stub.get_doc.assert_not_called()
		frappe_stub.db.set_value.assert_called_once()


	def test_ensure_vetedge_workspace_sidebar_updates_existing_sidebar(self):
		sidebar = SimpleNamespace(update=Mock(), save=Mock())
		exists = Mock(side_effect=lambda doctype, name: (doctype, name) in {("DocType", "Workspace Sidebar"), ("Workspace Sidebar", "VetEdge")})
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=exists),
			get_doc=Mock(return_value=sidebar),
			cache=SimpleNamespace(delete_key=Mock()),
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
