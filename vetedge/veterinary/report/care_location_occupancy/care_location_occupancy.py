from vetedge.services.hospitalisation_reports import get_care_location_occupancy_report


def execute(filters=None):
	return get_care_location_occupancy_report(filters)
