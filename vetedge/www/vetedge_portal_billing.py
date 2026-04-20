from vetedge.www.vetedge_portal import get_context as get_owner_portal_context


def get_context(context):
	context = get_owner_portal_context(context)
	context.title = "Billing"
	context.owner_portal_page = "billing"
	context.portal_subtitle = "Outstanding and paid invoices for your account."
	return context
