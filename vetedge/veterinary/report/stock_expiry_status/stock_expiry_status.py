from vetedge.services.reporting_catalog import require_reporting_entitlement
from vetedge.services.stock_expiry_monitor import execute_report
from vetedge.services.stock_expiry_scope import normalize_stock_expiry_branch_scope


def execute(filters=None):
	require_reporting_entitlement("Stock Expiry Status", scope_type="report")
	return execute_report(normalize_stock_expiry_branch_scope(filters))
