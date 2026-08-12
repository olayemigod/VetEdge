from vetedge.services.service_revenue import service_revenue_report


def execute(filters=None):
	return service_revenue_report(filters)
