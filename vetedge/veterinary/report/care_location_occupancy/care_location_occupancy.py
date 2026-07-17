from vetedge.services.hospitalisation_reports import get_care_location_occupancy_report
from vetedge.services.report_insights import build_report_summary


def execute(filters=None):
	columns, data = get_care_location_occupancy_report(filters)
	return columns, data, None, None, build_report_summary("Care Location Occupancy", data, filters)
