from vetedge.services.hospitalisation_reports import get_pending_hospitalisation_actions


def execute(filters=None):
	return get_pending_hospitalisation_actions(filters)
