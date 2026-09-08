import frappe

from vetedge.install import ensure_veterinary_desktop_icon_home


def execute() -> None:
	"""Apply the Veterinary launcher label and invalidate production boot caches."""
	ensure_veterinary_desktop_icon_home()
	frappe.cache.delete_key("desktop_icons")
	frappe.cache.delete_key("bootinfo")
