from vetedge.services.hospitalisation_reports import get_hospitalisation_charge_report
from vetedge.services.report_insights import build_report_summary


def execute(filters=None):
	columns, data = get_hospitalisation_charge_report(filters)
	return columns, data, None, None, build_report_summary("Hospitalisation Charge Summary", data, filters)
