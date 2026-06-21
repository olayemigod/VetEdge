from vetedge.services.hospitalisation_reports import get_discharge_watch_report


def execute(filters=None):
	return get_discharge_watch_report(filters)
