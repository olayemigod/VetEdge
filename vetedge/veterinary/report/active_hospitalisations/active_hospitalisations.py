from vetedge.services.hospitalisation_reports import get_active_hospitalisations
from vetedge.services.report_insights import build_report_summary


def execute(filters=None):
	columns, data = get_active_hospitalisations(filters)
	return columns, data, None, None, build_report_summary("Active Hospitalisations", data, filters)
