from __future__ import annotations

from pathlib import Path

from vetedge.services import stock_expiry_scope

ROOT = Path(__file__).resolve().parents[1]


def test_stock_expiry_unmapped_branch_fails_closed(monkeypatch):
	monkeypatch.setattr(stock_expiry_scope, "get_branch_dispensary_warehouse", lambda *args, **kwargs: None)
	result = stock_expiry_scope.normalize_stock_expiry_branch_scope({"branch": "Branch A"})
	assert result["warehouse"] == stock_expiry_scope.UNMAPPED_BRANCH_WAREHOUSE


def test_stock_expiry_mismatched_warehouse_fails_closed(monkeypatch):
	monkeypatch.setattr(
		stock_expiry_scope,
		"get_branch_dispensary_warehouse",
		lambda *args, **kwargs: "Branch A Dispensary - VE",
	)
	result = stock_expiry_scope.normalize_stock_expiry_branch_scope(
		{"branch": "Branch A", "warehouse": "Branch B Dispensary - VE"}
	)
	assert result["warehouse"] == stock_expiry_scope.UNMAPPED_BRANCH_WAREHOUSE


def test_stock_expiry_mapped_branch_forces_canonical_warehouse(monkeypatch):
	monkeypatch.setattr(
		stock_expiry_scope,
		"get_branch_dispensary_warehouse",
		lambda *args, **kwargs: "Branch A Dispensary - VE",
	)
	result = stock_expiry_scope.normalize_stock_expiry_branch_scope({"branch": "Branch A"})
	assert result["warehouse"] == "Branch A Dispensary - VE"


def test_stock_expiry_public_paths_apply_fail_closed_scope():
	page = (ROOT / "veterinary/page/stock_expiry_monitor/stock_expiry_monitor.py").read_text()
	report = (ROOT / "veterinary/report/stock_expiry_status/stock_expiry_status.py").read_text()
	for source in (page, report):
		assert "normalize_stock_expiry_branch_scope" in source
	assert "UNMAPPED_BRANCH_WAREHOUSE" in page
