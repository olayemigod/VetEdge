import frappe
from pprint import pprint

def run():
	import frappe.boot
	from vetedge.coreedge_adapter import filter_bootinfo_for_coreedge_platform
	bootinfo = frappe.boot.get_bootinfo()
	filter_bootinfo_for_coreedge_platform(bootinfo)
	
	with open("/home/olayemigod/frappe-bench/apps/vetedge/diagnostic_result.txt", "w", encoding="utf-8") as f:
		f.write("=== WORKSPACE SIDEBAR ITEMS ===\n")
		sidebars = bootinfo.get("workspace_sidebar_item") or {}
		for k in ("vetedge", "veterinary"):
			f.write(f"\n[{k}]:\n")
			if k in sidebars:
				sb = sidebars[k]
				f.write(f"  label: {sb.get('label')}\n")
				f.write(f"  title: {sb.get('title')}\n")
				f.write(f"  name: {sb.get('name')}\n")
				f.write(f"  items count: {len(sb.get('items') or [])}\n")
			else:
				f.write("  Not found!\n")
		
		f.write("\n=== DESKTOP ICONS FOR VETEDGE ===\n")
		icons = [i for i in bootinfo.get("desktop_icons") or [] if i.get("app") == "vetedge"]
		for icon in icons:
			f.write(f"icon:\n")
			for key, val in icon.items():
				f.write(f"  {key}: {val}\n")


def dump_navigation_sources():
	from vetedge.coreedge_adapter import filter_bootinfo_for_coreedge_platform
	import frappe.boot

	def exists(doctype):
		return frappe.db.exists("DocType", doctype)

	def matching_rows(doctype, fields, extra_filters=None):
		if not exists(doctype):
			return []
		meta = frappe.get_meta(doctype)
		available_fields = ["name"]
		for field in fields:
			if field == "name" or meta.has_field(field):
				available_fields.append(field)
		fields = list(dict.fromkeys(available_fields))
		rows = frappe.get_all(doctype, fields=fields, filters=extra_filters or {}, limit_page_length=1000)
		matches = []
		needles = ("vetedge", "veterinary")
		for row in rows:
			text = " ".join(str(row.get(field) or "") for field in fields).lower()
			if any(needle in text for needle in needles):
				matches.append(dict(row))
		return matches

	data = {
		"hooks_add_to_apps_screen": frappe.get_hooks("add_to_apps_screen", app_name="vetedge"),
		"hooks_app_title": frappe.get_hooks("app_title", app_name="vetedge"),
		"desktop_icons": matching_rows(
			"Desktop Icon",
			[
				"name",
				"label",
				"app",
				"icon_type",
				"link_type",
				"link",
				"link_to",
				"parent_icon",
				"hidden",
				"standard",
				"idx",
			],
		),
		"workspace_sidebars": [],
		"workspaces": matching_rows(
			"Workspace",
			["name", "title", "label", "module", "app", "route", "public", "is_hidden"],
		),
		"pages": matching_rows("Page", ["name", "title", "module", "page_name", "standard", "system_page"]),
	}

	if exists("Workspace Sidebar"):
		for sidebar in matching_rows(
			"Workspace Sidebar",
			["name", "title", "app", "module", "for_user", "standard", "header_icon"],
		):
			doc = frappe.get_doc("Workspace Sidebar", sidebar["name"])
			items = []
			for item in doc.items:
				items.append(
					{
						"label": item.label,
						"type": item.type,
						"link_type": item.link_type,
						"link_to": item.link_to,
						"link": getattr(item, "url", None),
						"child": item.child,
						"idx": item.idx,
						"hidden": getattr(item, "hidden", None),
					}
				)
			sidebar["first_items"] = items[:15]
			sidebar["top_level"] = [item["label"] for item in items if not item["child"]]
			sidebar["first_link"] = next((item for item in items if item["type"] == "Link"), None)
			sidebar["patient_items"] = [item for item in items if item.get("link_to") == "Veterinary Patient"]
			data["workspace_sidebars"].append(sidebar)

	bootinfo = frappe.boot.get_bootinfo()
	filter_bootinfo_for_coreedge_platform(bootinfo)
	data["boot_desktop_icons"] = [
		dict(icon)
		for icon in bootinfo.get("desktop_icons") or []
		if "vetedge" in str(icon).lower() or "veterinary" in str(icon).lower()
	]
	data["boot_app_data"] = [
		dict(app)
		for app in bootinfo.get("app_data") or []
		if "vetedge" in str(app).lower() or "veterinary" in str(app).lower()
	]
	data["boot_workspace_sidebars"] = {}
	for key, sidebar in (bootinfo.get("workspace_sidebar_item") or {}).items():
		if key in ("vetedge", "veterinary") or "vetedge" in key or "veterinary" in key:
			items = sidebar.get("items") or []
			data["boot_workspace_sidebars"][key] = {
				"label": sidebar.get("label"),
				"app": sidebar.get("app"),
				"module": sidebar.get("module"),
				"first_items": items[:15],
				"top_level": [item.get("label") for item in items if not item.get("child")],
				"first_link": next((item for item in items if item.get("type") == "Link"), None),
			}

	return data
