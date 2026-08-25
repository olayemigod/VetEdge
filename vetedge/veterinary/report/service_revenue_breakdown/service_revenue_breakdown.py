from vetedge.services.report_visibility import normalize_report_filters
from vetedge.services.service_revenue import service_revenue_report


def execute(filters=None):
	return service_revenue_report(normalize_report_filters("Revenue Summary", filters))
