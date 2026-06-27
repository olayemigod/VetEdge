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
