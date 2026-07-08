from vetedge.services.hospitalisation_reports import get_pending_hospitalisation_actions
from vetedge.services.report_insights import build_report_summary


def execute(filters=None):
	columns, data = get_pending_hospitalisation_actions(filters)
	return columns, data, None, None, build_report_summary("Pending Hospitalisation Actions", data, filters)
