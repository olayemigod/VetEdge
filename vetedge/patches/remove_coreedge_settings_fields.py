# -*- coding: utf-8 -*-
import frappe

def execute():
	fields_to_remove = [
		"coreedge_platform_section",
		"deployment_mode",
		"enable_coreedge_platform",
		"coreedge_product_app",
		"fail_closed_when_coreedge_missing"
	]
	
	frappe.db.sql(
		"DELETE FROM `tabSingles` WHERE `doctype` = 'Veterinary Settings' AND `field` IN %s",
		(tuple(fields_to_remove),)
	)
	frappe.db.commit()
