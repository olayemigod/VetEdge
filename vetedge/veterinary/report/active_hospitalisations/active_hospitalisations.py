from vetedge.services.hospitalisation_reports import get_active_hospitalisations


def execute(filters=None):
	return get_active_hospitalisations(filters)
