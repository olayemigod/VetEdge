from vetedge.services.hospitalisation_reports import get_hospitalisation_charge_report


def execute(filters=None):
	return get_hospitalisation_charge_report(filters)
