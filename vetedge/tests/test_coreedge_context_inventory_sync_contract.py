from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _source() -> str:
	return (ROOT / "services/coreedge_context_sync.py").read_text(encoding="utf-8")


def test_context_sync_uses_remote_service_without_coreedge_package_dependency():
	source = _source()
	assert "import coreedge" not in source
	assert "from coreedge" not in source
	assert "/api/method/coreedge.api.v1.service_context.submit_context_inventory" in source
	assert "requests.post(" in source
	assert '"Authorization"' in source
	assert "token {config[" in source


def test_context_sync_requires_private_service_configuration_and_https_by_default():
	source = _source()
	for key in (
		"coreedge_service_url",
		"coreedge_service_site_identifier",
		"coreedge_service_api_key",
		"coreedge_service_api_secret",
		"coreedge_service_timeout_seconds",
		"coreedge_service_allow_insecure_http",
	):
		assert key in source
	assert 'parts.scheme != "https"' in source
	assert "_MAX_TIMEOUT_SECONDS = 60" in source


def test_context_sync_submits_full_local_normalizer_output_and_sanitizes_product_metadata():
	source = _source()
	assert "get_context_reconciliation_rows()" in source
	for key in (
		'"local_doctype"',
		'"local_name"',
		'"local_label"',
		'"local_code"',
		'"company"',
		'"active"',
		'"normalization_issue"',
	):
		assert key in source
	for forbidden in (
		'"platform_branch_id"',
		'"source_profile"',
		'"company_resolution_sources"',
	):
		assert forbidden not in source


def test_context_sync_is_operator_only_and_hour_bucket_idempotent():
	source = _source()
	assert '"System Manager"' in source
	assert "frappe.session.user == \"Administrator\"" in source
	assert 'strftime("%Y%m%d%H")' in source
	assert "hashlib.sha256" in source
	assert "idempotency_key" in source


def test_context_sync_does_not_log_or_return_configured_secret():
	source = _source()
	assert "frappe.log_error" not in source
	assert "print(" not in source
	assert '"api_secret_configured"' in source
	assert '"api_secret": values["coreedge_service_api_secret"]' in source
