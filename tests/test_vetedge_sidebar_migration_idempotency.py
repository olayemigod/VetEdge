from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "vetedge" / "install" / "dashboard.py"


def load_dashboard_module():
	frappe_stub = SimpleNamespace(
		_=lambda value, *args, **kwargs: value,
		flags=SimpleNamespace(in_import=False),
	)
	modules_stub = SimpleNamespace()
	import_file_stub = SimpleNamespace(import_file_by_path=lambda *args, **kwargs: None)

	with patch.dict(
		sys.modules,
		{
			"frappe": frappe_stub,
			"frappe.modules": modules_stub,
			"frappe.modules.import_file": import_file_stub,
		},
	):
		spec = importlib.util.spec_from_file_location("vetedge_sidebar_dashboard_contract", MODULE_PATH)
		module = importlib.util.module_from_spec(spec)
		assert spec and spec.loader
		spec.loader.exec_module(module)
	return module


def test_financial_dashboard_does_not_force_import_sidebar_file():
	dashboard = load_dashboard_module()
	assert ("workspace_sidebar", "vetedge.json") not in dashboard.FINANCIAL_DASHBOARD_FILES


def test_matching_sidebar_is_not_saved_again():
	dashboard = load_dashboard_module()
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
	assert frappe_stub.flags.in_import is False


def test_changed_sidebar_save_suppresses_standard_file_export():
	dashboard = load_dashboard_module()
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

	sidebar.save.assert_called_once_with(ignore_permissions=True)
	assert save_states == [True]
	assert frappe_stub.flags.in_import is False


def test_missing_sidebar_insert_suppresses_standard_file_export():
	dashboard = load_dashboard_module()
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

	doc.insert.assert_called_once_with(ignore_permissions=True)
	assert insert_states == [True]
	assert frappe_stub.flags.in_import is False
