from vetedge.www.vetedge_portal import get_context as get_owner_portal_context


def get_context(context):
	context = get_owner_portal_context(context)
	context.title = "Medical History"
	context.owner_portal_page = "history"
	context.portal_subtitle = "Safe consultation summaries shared by the clinic."
	return context
