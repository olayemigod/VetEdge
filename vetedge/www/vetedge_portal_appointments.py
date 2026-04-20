from vetedge.www.vetedge_portal import get_context as get_owner_portal_context


def get_context(context):
	context = get_owner_portal_context(context)
	context.title = "Appointments"
	context.owner_portal_page = "appointments"
	context.portal_subtitle = "Request a visit and review upcoming appointments."
	return context
