from vetedge.www.vetedge_portal import get_context as get_owner_portal_context


def get_context(context):
	context = get_owner_portal_context(context)
	context.title = "My Pets"
	context.owner_portal_page = "pets"
	context.portal_subtitle = "Registered pets linked to your account."
	return context
