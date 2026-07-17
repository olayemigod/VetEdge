from vetedge.services.hospitalisation_reports import get_discharge_watch_report
from vetedge.services.report_insights import build_report_summary


def execute(filters=None):
	columns, data = get_discharge_watch_report(filters)
	return columns, data, None, None, build_report_summary("Hospitalisation Discharge Watch", data, filters)
