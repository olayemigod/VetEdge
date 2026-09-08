from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_stock_expiry_shell_uses_server_subscription_tier_context():
    source = (ROOT / "public/js/vetedge_stock_expiry_monitor/VetedgeStockExpiryMonitor.vue").read_text(encoding="utf-8")
    assert ':tier="capabilities.report_tier || \'\'"' in source
    assert ':subscriptionEntitled="capabilities.subscription_entitled !== false"' in source
    assert "VetEdgeReportingCapabilities.get('Stock Expiry Status', 'report'" in source


def test_dashboard_shell_adapter_uses_server_subscription_tier_context():
    source = (ROOT / "public/js/vetedge_dashboard_alignment.bundle.js").read_text(encoding="utf-8")
    assert 'tier: this.capabilities.report_tier || ""' in source
    assert 'subscriptionEntitled: this.capabilities.subscription_entitled !== false' in source
    assert 'scope_type: "dashboard"' in source


def test_report_center_must_be_migrated_to_capability_driven_report_shell():
    source = (ROOT / "veterinary/page/vetedge_report_center/vetedge_report_center.js").read_text(encoding="utf-8")

    # Acceptance rule for the next Report Center migration slice: the host must
    # consume the canonical report shell and server-authoritative capability
    # context rather than permanently rendering manual Print/Export buttons.
    assert "EdgeReportShell" in source, (
        "VetEdge Report Center still uses the legacy EdgePageLayout/manual-action composition. "
        "Migrate it to EdgeReportShell before marking the reporting-shell programme accepted."
    )
    assert "get_shell_capabilities" in source or "VetEdgeReportingCapabilities" in source
