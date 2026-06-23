# VetEdge DocType & Report Rename Plan (V1.1 - Updated)

This plan outlines the final, updated implementation scope for renaming all remaining `VetEdge`-prefixed DocTypes and Reports to generic `Veterinary` equivalents. This completely removes vendor-specific branding from user-facing components while ensuring database consistency.

No clinical VetEdge-prefixed DocTypes (such as Patient, Consultation, Appointment, Lab, Vaccination, Hospitalisation) were found in this inventory; they are already prefixed with `Veterinary` and are therefore **excluded** from this rename phase.

---

## 1. Scope of Renames

### 1.1 DocTypes to Rename

| Current DocType Name | New DocType Name | Internal Name (Current) | New Internal Name |
| :--- | :--- | :--- | :--- |
| **VetEdge License Profile** | **Veterinary License Profile** | `vetedge_license_profile` | `veterinary_license_profile` |
| **VetEdge Notification Log** | **Veterinary Notification Log** | `vetedge_notification_log` | `veterinary_notification_log` |
| **VetEdge Notification Preference** | **Veterinary Notification Preference** | `vetedge_notification_preference` | `veterinary_notification_preference` |
| **VetEdge Role Bundle** | **Veterinary Role Bundle** | `vetedge_role_bundle` | `veterinary_role_bundle` |
| **VetEdge Role Bundle Role** | **Veterinary Role Bundle Role** | `vetedge_role_bundle_role` | `veterinary_role_bundle_role` |

### 1.2 Reports to Rename

| Current Report Name | New Report Name | Internal Name (Current) | New Internal Name |
| :--- | :--- | :--- | :--- |
| **VetEdge Notification Event Registry** | **Veterinary Notification Event Registry** | `vetedge_notification_event_registry` | `veterinary_notification_event_registry` |

### 1.3 Child Table Option Update
- Within the **Veterinary Role Bundle** DocType (formerly `VetEdge Role Bundle`), the field `roles` (type `Table`) options must be updated from `VetEdge Role Bundle Role` to point to **`Veterinary Role Bundle Role`**.

---

## 2. Idempotent Migration Patch Strategy

The patch must be run automatically during the deploy cycle. To ensure safety and idempotence, the patch will check for the existence of the old doctype/report and the non-existence of the new doctype/report before performing `frappe.rename_doc`.

### Patch Script Location: `vetedge/patches/v1_1/rename_vetedge_doctypes_and_reports.py`
```python
import frappe

def execute():
	# 1. Rename DocTypes
	doctypes_to_rename = [
		("VetEdge License Profile", "Veterinary License Profile"),
		("VetEdge Notification Log", "Veterinary Notification Log"),
		("VetEdge Notification Preference", "Veterinary Notification Preference"),
		("VetEdge Role Bundle", "Veterinary Role Bundle"),
		("VetEdge Role Bundle Role", "Veterinary Role Bundle Role"),
	]
	for old_dt, new_dt in doctypes_to_rename:
		if frappe.db.exists("DocType", old_dt) and not frappe.db.exists("DocType", new_dt):
			frappe.rename_doc("DocType", old_dt, new_dt, force=True)
			
	# 2. Rename Reports
	reports_to_rename = [
		("VetEdge Notification Event Registry", "Veterinary Notification Event Registry")
	]
	for old_rep, new_rep in reports_to_rename:
		if frappe.db.exists("Report", old_rep) and not frappe.db.exists("Report", new_rep):
			frappe.rename_doc("Report", old_rep, new_rep, force=True)
```

Add this patch entry to `vetedge/patches.txt` for automatic execution on migrate.

---

## 3. File-Based Definitions to Modify

The following directories and files must be updated on the disk:
1. **Directories**:
   - `vetedge/veterinary/doctype/vetedge_license_profile/` -> `veterinary_license_profile/`
   - `vetedge/veterinary/doctype/vetedge_notification_log/` -> `veterinary_notification_log/`
   - `vetedge/veterinary/doctype/vetedge_notification_preference/` -> `veterinary_notification_preference/`
   - `vetedge/veterinary/doctype/vetedge_role_bundle/` -> `veterinary_role_bundle/`
   - `vetedge/veterinary/doctype/vetedge_role_bundle_role/` -> `veterinary_role_bundle_role/`
   - `vetedge/veterinary/report/vetedge_notification_event_registry/` -> `veterinary_notification_event_registry/`
2. **Metadata Files**:
   - Rename JSON files inside the directories to match the new names.
   - Update file names for controllers `.py` and JS files.
   - Edit the DocType `.json` files to update:
     - `name` attributes.
     - `options` attributes (for child tables and links).
3. **Workspace/Sidebar Configuration**:
   - Update `vetedge/workspace_sidebar/vetedge.json` references to point to the new DocType names.
4. **Codebase references**:
   - Update `vetedge/hooks.py` permission query mappings.
   - Update `vetedge/services/notifications.py` and `vetedge/services/role_bundles.py` references.
   - Update all test files (`test_notification_structure.py`, `test_role_bundles.py`, `test_workspace_sidebar.py`) to reference the new DocType/Report names.

---

## 4. Preservations (What NOT to Rename)

To maintain platform stability, keep the following technical naming intact:
- App directory name `/apps/vetedge` and Python import path `vetedge` package.
- Installed app name `vetedge` configuration in `hooks.py`.
- Product adapter context properties, site config settings (`product_app = "vetedge"`).
- Whitelisted method path names.
- All technical lowercase occurrences of the word `vetedge` (e.g. variables, database prefixes).

---

## 5. Verification & Validation Plan

### 5.1 Unit Tests to Add
Add unit tests verifying that:
- The new `Veterinary ...` DocTypes exist.
- The old `VetEdge ...` DocTypes do not exist in the database.
- `Veterinary Role Bundle` child table `roles` field options are correctly set to `Veterinary Role Bundle Role`.
- The new `Veterinary Notification Event Registry` report exists.
- The old report has been removed and is no longer user-facing.
- Notification logs and role bundles continue to operate as expected.

### 5.2 Focused Test Runs
Run the test suites to ensure no regressions:
```bash
bench --site vetedge.local run-tests --app vetedge --test vetedge.tests.test_branding
bench --site vetedge.local run-tests --app coreedge --test coreedge.coreedge.tests.test_branding
bench --site vetedge.local run-tests --app coreedge --test coreedge.coreedge.tests.test_platform_role_protection
```

### 5.3 Technical Naming Validation (Grep Checks)
After coding the renames, execute these final grep commands to assert no user-facing branding configurations remain:
```bash
grep -R '"name": "VetEdge ' vetedge --include="*.json"
grep -R '"doctype": "VetEdge ' vetedge --include="*.json"
grep -R 'options": "VetEdge ' vetedge --include="*.json"
```
*Expected output: Empty results.*
